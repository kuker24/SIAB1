"""Offline package route for resilient exam runtime.

The public path remains under ``/api/exams`` while keeping package generation
out of the large exam routes module.
"""

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.exam_runtime_cache import (
    get_exam_question_count_cached as _get_exam_question_count_cached,
    get_session_answer_count_cached as _get_session_answer_count_cached,
)
from app.core.exam_session_helpers import calculate_effective_timer, resolve_timer_context
from app.core.redis_pubsub import get_session_data
from app.core.security import AuthenticatedUser, get_current_user_hot_path
from app.database import get_db_read
from app.models.exam import Exam
from app.models.session import ExamSession
from app.services.exam_service import ExamService

router = APIRouter(prefix="/api/exams", tags=["Exam Offline Package"])

OFFLINE_PACKAGE_TTL_SECONDS = 30 * 60


def get_exam_service_read(db: AsyncSession = Depends(get_db_read)) -> ExamService:
    return ExamService(db)


def _sign_offline_package_payload(session_id: int, payload: Dict[str, Any]) -> str:
    secret_value = (
        (settings.secret_key or "").strip()
        or (settings.jwt_secret_key or "").strip()
        or "exam-offline-package-fallback-secret"
    )
    secret = secret_value.encode("utf-8")
    canonical_payload = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    payload_digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    signature_input = f"{session_id}:{payload_digest}".encode("utf-8")
    return hmac.new(secret, signature_input, hashlib.sha256).hexdigest()


@router.get("/session/{session_id}/offline-package")
async def get_offline_exam_package(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db_read),
    exam_service: ExamService = Depends(get_exam_service_read),
):
    """
    Build a signed offline package snapshot for resilient mobile exam runtime.

    Package includes current timer state, latest saved answers, and question
    payload without answer keys/correctness. Signature allows client-side
    integrity checks before using cached data while offline.
    """
    result = await db.execute(
        select(ExamSession)
        .options(
            selectinload(ExamSession.exam).selectinload(Exam.creator),
            selectinload(ExamSession.answers),
        )
        .where(
            ExamSession.id == session_id,
            ExamSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

    if session.status not in ["in_progress", "active"]:
        raise HTTPException(
            status_code=409,
            detail="Paket offline hanya tersedia untuk sesi ujian aktif",
        )

    answered_count = await _get_session_answer_count_cached(db, session.id)
    total_questions = await _get_exam_question_count_cached(db, session.exam_id)

    await db.commit()
    redis_data = await get_session_data(session.id)
    started_at, total_seconds, total_paused = resolve_timer_context(session, redis_data)
    elapsed_seconds, remaining_seconds = calculate_effective_timer(
        started_at=started_at,
        total_seconds=total_seconds,
        total_paused_seconds=total_paused,
    )
    is_expired = remaining_seconds <= 0

    questions_payload = await exam_service.get_questions_payload(session.exam_id)
    if not questions_payload:
        raise HTTPException(status_code=404, detail="Soal ujian tidak ditemukan")

    saved_answers: Dict[str, Any] = {}
    for answer in session.answers:
        question_id = str(answer.question_id)
        metadata = dict(answer.answer_metadata or {})
        if metadata.get("statement_answers"):
            saved_answers[question_id] = metadata.get("statement_answers")
        elif answer.selected_option_ids:
            saved_answers[question_id] = answer.selected_option_ids
        elif answer.answer_text is not None and answer.answer_text.strip():
            saved_answers[question_id] = answer.answer_text
        elif answer.selected_option_id is not None:
            saved_answers[question_id] = answer.selected_option_id

    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=OFFLINE_PACKAGE_TTL_SECONDS)

    package_payload: Dict[str, Any] = {
        "session": {
            "session_id": session.id,
            "exam_id": session.exam_id,
            "status": session.status,
            "issued_at": issued_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "time_remaining_seconds": remaining_seconds,
            "elapsed_seconds": elapsed_seconds,
            "total_seconds": total_seconds,
            "is_expired": is_expired,
            "violation_count": int(session.violation_count or 0),
            "emergency_exit_allowed": bool(session.emergency_exit_allowed),
        },
        "exam": {
            "title": session.exam.title,
            "duration_minutes": int(session.exam.duration_minutes or 0),
            "start_time": session.exam.start_time.isoformat() if session.exam.start_time else None,
            "end_time": session.exam.end_time.isoformat() if session.exam.end_time else None,
            "show_results": bool(session.exam.show_results),
            "show_teacher_name": bool(session.exam.show_teacher_name),
            "teacher_name": session.exam.creator.full_name if session.exam.creator else None,
            "shuffle_questions": bool(session.exam.shuffle_questions),
            "shuffle_options": bool(session.exam.shuffle_options),
            "show_exam_timer": bool(getattr(session.exam, "show_exam_timer", True)),
        },
        "progress": {
            "answered_count": answered_count,
            "total_questions": total_questions,
            "saved_answers": saved_answers,
            "last_question_id": max(
                (int(question_id) for question_id in saved_answers.keys()),
                default=None,
            ),
        },
        "questions": questions_payload,
        "runtime_policy": {
            "auto_save_interval_ms": 30000,
            "answer_sync_debounce_ms": 5000,
            "offline_first": True,
        },
    }

    signature = _sign_offline_package_payload(session.id, package_payload)
    package_hash = hashlib.sha256(
        json.dumps(
            package_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    return {
        "status": "ok",
        "package_id": f"offline-{session.id}-{package_hash[:12]}",
        "signature": signature,
        "signature_algorithm": "HMAC-SHA256",
        "package_hash": package_hash,
        "ttl_seconds": OFFLINE_PACKAGE_TTL_SECONDS,
        "server_time": issued_at.isoformat(),
        "payload": package_payload,
    }
