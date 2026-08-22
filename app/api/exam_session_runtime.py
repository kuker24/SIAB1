"""Hot-path exam session runtime routes.

These endpoints are separated from ``app.api.exams`` to keep the large exam
module focused while preserving the public ``/api/exams/...`` paths.
"""

import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exam_runtime_cache import (
    get_exam_question_count_cached as _get_exam_question_count_cached,
    get_session_answer_count_cached as _get_session_answer_count_cached,
    get_user_display_name_cached as _get_user_display_name_cached,
    should_update_session_activity as _should_update_session_activity,
)
from app.core.exam_runtime_state import get_answered_count_from_set as _get_answered_count_from_set
from app.core.exam_session_helpers import (
    calculate_effective_timer,
    parse_iso_datetime_utc,
    resolve_timer_context,
    safe_int,
)
from app.core.redis_pubsub import (
    get_session_answers,
    get_session_data,
    store_session_data,
    update_session_activity,
)
from app.core.security import AuthenticatedUser, create_session_poll_token, get_current_user_hot_path
from app.core.session_recovery import evaluate_session_recovery
from app.database import get_db_read
from app.models.exam import Exam
from app.models.session import ExamLog, ExamSession
from app.schemas.answer import SessionStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exams", tags=["Exam Session Runtime"])

SESSION_POLL_TOKEN_EXPIRES_MINUTES = 15


class PreciseTimerResponse(BaseModel):
    """Response with second-accurate remaining time."""

    session_id: int
    remaining_seconds: int
    elapsed_seconds: int
    total_seconds: int
    started_at: str
    is_expired: bool


class SessionResumeResponse(BaseModel):
    """Response for session resume after disconnection."""

    session_id: int
    exam_id: int
    exam_title: str
    remaining_seconds: int
    elapsed_seconds: int
    total_seconds: int
    is_expired: bool
    saved_answers: dict
    answered_count: int
    total_questions: int
    last_question_id: Optional[int] = None
    can_resume: bool
    message: str
    recovery_category: Optional[str] = None
    recovery_message: Optional[str] = None
    session_poll_token: Optional[str] = None
    session_poll_token_expires_minutes: Optional[int] = None


@router.get("/session/{session_id}/status", response_model=SessionStatusResponse)
async def get_session_status(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db_read),
):
    """Get current session status."""
    session_result = await db.execute(
        select(
            ExamSession.id.label("session_id"),
            ExamSession.exam_id.label("exam_id"),
            ExamSession.start_time.label("start_time"),
            ExamSession.end_time.label("end_time"),
            ExamSession.status.label("status"),
            ExamSession.violation_count.label("violation_count"),
            ExamSession.total_paused_seconds.label("total_paused_seconds"),
            ExamSession.is_paused.label("is_paused"),
            ExamSession.paused_at.label("paused_at"),
            ExamSession.terminated_by_admin.label("terminated_by_admin"),
            ExamSession.emergency_exit_allowed.label("emergency_exit_allowed"),
            Exam.is_globally_paused.label("is_globally_paused"),
            Exam.globally_paused_by.label("globally_paused_by"),
            Exam.globally_paused_at.label("globally_paused_at"),
            Exam.duration_minutes.label("duration_minutes"),
        )
        .join(Exam, Exam.id == ExamSession.exam_id)
        .where(
            ExamSession.id == session_id,
            ExamSession.user_id == current_user.id,
        )
    )
    session_row = session_result.mappings().one_or_none()
    if not session_row:
        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

    session_exam_id = int(session_row["exam_id"])
    session_status = str(session_row["status"])
    session_violation_count = int(session_row["violation_count"] or 0)

    redis_data = await get_session_data(session_id)
    redis_belongs_to_user = bool(
        redis_data and safe_int((redis_data or {}).get("user_id")) == current_user.id
    )

    total_questions = safe_int((redis_data or {}).get("total_questions")) if redis_belongs_to_user else None
    if total_questions is None or total_questions <= 0:
        total_questions = await _get_exam_question_count_cached(db, session_exam_id)

    answered_count: Optional[int] = None
    if redis_belongs_to_user and not bool((redis_data or {}).get("answered_count_stale")):
        answered_count = safe_int((redis_data or {}).get("answered_count"))
    if answered_count is None:
        try:
            answered_count = await _get_answered_count_from_set(session_id)
        except Exception as runtime_exc:
            logger.debug(
                "SESSION-STATUS | session=%s | runtime answered_count read failed: %s",
                session_id,
                str(runtime_exc),
            )
        if answered_count is None:
            answered_count = await _get_session_answer_count_cached(db, session_id)

    is_paused = bool(session_row["is_paused"]) or bool(session_row["is_globally_paused"])
    paused_by = None
    pause_message = None

    if is_paused:
        pause_message = "Ujian sedang di-pause oleh pengawas"
        if bool(session_row["is_globally_paused"]) and session_row["globally_paused_by"]:
            paused_by = await _get_user_display_name_cached(
                db,
                safe_int(session_row["globally_paused_by"]),
            )

    await db.commit()

    if not redis_belongs_to_user:
        redis_data = {
            "session_id": session_id,
            "user_id": current_user.id,
            "exam_id": session_exam_id,
            "start_time": session_row["start_time"].isoformat() if session_row["start_time"] else None,
            "end_time": session_row["end_time"].isoformat() if session_row["end_time"] else None,
            "duration_minutes": safe_int(session_row["duration_minutes"]) or 0,
            "status": session_status,
            "answered_count": int(answered_count),
            "answered_count_stale": False,
            "total_questions": int(total_questions),
            "violation_count": session_violation_count,
            "total_paused_seconds": safe_int(session_row["total_paused_seconds"]) or 0,
        }
        redis_belongs_to_user = True
        try:
            await store_session_data(session_id, redis_data)
        except Exception as cache_exc:
            logger.debug(
                "SESSION-STATUS | session=%s | failed to create redis snapshot: %s",
                session_id,
                str(cache_exc),
            )

    if redis_belongs_to_user and redis_data is not None:
        redis_changed = False
        if safe_int(redis_data.get("answered_count")) != int(answered_count):
            redis_data["answered_count"] = int(answered_count)
            redis_changed = True
        if bool(redis_data.get("answered_count_stale")):
            redis_data["answered_count_stale"] = False
            redis_changed = True
        if safe_int(redis_data.get("total_questions")) != int(total_questions):
            redis_data["total_questions"] = int(total_questions)
            redis_changed = True
        if safe_int(redis_data.get("session_id")) != session_id:
            redis_data["session_id"] = session_id
            redis_changed = True
        if safe_int(redis_data.get("exam_id")) != session_exam_id:
            redis_data["exam_id"] = session_exam_id
            redis_changed = True
        if str(redis_data.get("status") or "") != session_status:
            redis_data["status"] = session_status
            redis_changed = True
        end_time_value = session_row["end_time"].isoformat() if session_row["end_time"] else None
        if redis_data.get("end_time") != end_time_value:
            redis_data["end_time"] = end_time_value
            redis_changed = True
        if safe_int(redis_data.get("violation_count")) != session_violation_count:
            redis_data["violation_count"] = session_violation_count
            redis_changed = True
        if redis_changed:
            try:
                await store_session_data(session_id, redis_data)
            except Exception as cache_exc:
                logger.debug(
                    "SESSION-STATUS | session=%s | failed to refresh redis snapshot: %s",
                    session_id,
                    str(cache_exc),
                )

    timer_view = SimpleNamespace(
        start_time=(
            parse_iso_datetime_utc((redis_data or {}).get("start_time"))
            or session_row["start_time"]
        ),
        total_paused_seconds=safe_int(session_row["total_paused_seconds"]) or 0,
        is_paused=bool(session_row["is_paused"]),
        paused_at=session_row["paused_at"],
        exam=SimpleNamespace(
            duration_minutes=safe_int(session_row["duration_minutes"]) or 0,
            is_globally_paused=bool(session_row["is_globally_paused"]),
            globally_paused_at=session_row["globally_paused_at"],
        ),
    )
    started_at, total_seconds, total_paused = resolve_timer_context(timer_view, redis_data)
    _effective_elapsed, time_remaining = calculate_effective_timer(
        started_at=started_at,
        total_seconds=total_seconds,
        total_paused_seconds=total_paused,
    )

    if session_status == "in_progress" and _should_update_session_activity(session_id):
        try:
            await update_session_activity(session_exam_id, current_user.id, {
                "last_active": datetime.now(timezone.utc).isoformat(),
                "status": "online",
            })
        except Exception as exc:
            logger.warning("Failed to update session activity: %s", exc)

    kick_reason = None
    emergency_exit_allowed = bool(session_row["emergency_exit_allowed"])
    terminated_by_admin = bool(session_row["terminated_by_admin"])
    is_force_kick = (
        session_status == "kicked"
        or (
            session_status == "terminated"
            and terminated_by_admin
            and not emergency_exit_allowed
        )
    )
    if is_force_kick:
        kick_reason = "Dikeluarkan oleh pengawas"

    reported_status = "kicked" if is_force_kick else session_status

    return SessionStatusResponse(
        session_id=session_id,
        status=reported_status,
        time_remaining_seconds=time_remaining,
        answered_count=int(answered_count),
        total_questions=int(total_questions),
        violation_count=session_violation_count,
        is_paused=is_paused,
        paused_by=paused_by,
        pause_message=pause_message,
        kick_reason=kick_reason,
        emergency_exit_allowed=emergency_exit_allowed,
        terminated_by_admin=terminated_by_admin,
        session_poll_token=create_session_poll_token(
            session_id=session_id,
            user_id=current_user.id,
            expires_minutes=SESSION_POLL_TOKEN_EXPIRES_MINUTES,
        ),
        session_poll_token_expires_minutes=SESSION_POLL_TOKEN_EXPIRES_MINUTES,
    )


@router.get("/session/{session_id}/remaining-time", response_model=PreciseTimerResponse)
async def get_remaining_time(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db_read),
):
    """Get precise remaining time for exam session."""
    redis_data = await get_session_data(session_id)
    redis_belongs_to_user = bool(
        redis_data and safe_int((redis_data or {}).get("user_id")) == current_user.id
    )

    if redis_belongs_to_user:
        redis_duration_seconds = safe_int((redis_data or {}).get("duration_seconds")) or 0
        redis_duration_minutes = safe_int((redis_data or {}).get("duration_minutes")) or 0
        if redis_duration_minutes <= 0 and redis_duration_seconds > 0:
            redis_duration_minutes = max(1, redis_duration_seconds // 60)

        redis_start_time = parse_iso_datetime_utc((redis_data or {}).get("start_time"))
        if redis_start_time and redis_duration_minutes > 0:
            timer_view = SimpleNamespace(
                start_time=redis_start_time,
                total_paused_seconds=safe_int((redis_data or {}).get("total_paused_seconds")) or 0,
                is_paused=bool((redis_data or {}).get("paused", False)),
                paused_at=None,
                exam=SimpleNamespace(
                    duration_minutes=redis_duration_minutes,
                    is_globally_paused=False,
                    globally_paused_at=None,
                ),
            )
            started_at, total_seconds, total_paused = resolve_timer_context(timer_view, redis_data)
            effective_elapsed, remaining = calculate_effective_timer(
                started_at=started_at,
                total_seconds=total_seconds,
                total_paused_seconds=total_paused,
            )
            return PreciseTimerResponse(
                session_id=session_id,
                remaining_seconds=remaining,
                elapsed_seconds=effective_elapsed,
                total_seconds=total_seconds,
                started_at=started_at.isoformat(),
                is_expired=remaining <= 0,
            )

    session_result = await db.execute(
        select(
            ExamSession.start_time.label("start_time"),
            ExamSession.total_paused_seconds.label("total_paused_seconds"),
            ExamSession.is_paused.label("is_paused"),
            ExamSession.paused_at.label("paused_at"),
            Exam.duration_minutes.label("duration_minutes"),
            Exam.is_globally_paused.label("is_globally_paused"),
            Exam.globally_paused_at.label("globally_paused_at"),
        )
        .join(Exam, Exam.id == ExamSession.exam_id)
        .where(
            ExamSession.id == session_id,
            ExamSession.user_id == current_user.id,
        )
    )
    session_row = session_result.mappings().one_or_none()
    if not session_row:
        raise HTTPException(404, "Sesi ujian tidak ditemukan")

    await db.commit()
    timer_view = SimpleNamespace(
        start_time=session_row["start_time"],
        total_paused_seconds=safe_int(session_row["total_paused_seconds"]) or 0,
        is_paused=bool(session_row["is_paused"]),
        paused_at=session_row["paused_at"],
        exam=SimpleNamespace(
            duration_minutes=safe_int(session_row["duration_minutes"]) or 0,
            is_globally_paused=bool(session_row["is_globally_paused"]),
            globally_paused_at=session_row["globally_paused_at"],
        ),
    )
    started_at, total_seconds, total_paused = resolve_timer_context(timer_view, redis_data)
    effective_elapsed, remaining = calculate_effective_timer(
        started_at=started_at,
        total_seconds=total_seconds,
        total_paused_seconds=total_paused,
    )

    return PreciseTimerResponse(
        session_id=session_id,
        remaining_seconds=remaining,
        elapsed_seconds=effective_elapsed,
        total_seconds=total_seconds,
        started_at=started_at.isoformat(),
        is_expired=remaining <= 0,
    )


@router.get("/session/{session_id}/resume", response_model=SessionResumeResponse)
async def resume_session(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db_read),
):
    """Resume exam session after network disconnection."""
    result = await db.execute(
        select(ExamSession)
        .options(
            selectinload(ExamSession.exam).selectinload(Exam.questions),
            selectinload(ExamSession.answers),
        )
        .where(
            ExamSession.id == session_id,
            ExamSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "Sesi ujian tidak ditemukan")

    logs_result = await db.execute(
        select(ExamLog)
        .where(ExamLog.session_id == session_id)
        .order_by(ExamLog.created_at.desc(), ExamLog.id.desc())
        .limit(30)
    )
    session_logs = logs_result.scalars().all()
    recovery_status = evaluate_session_recovery(session, session_logs)

    if session.status in ["completed", "submitted"]:
        return SessionResumeResponse(
            session_id=session_id,
            exam_id=session.exam.id,
            exam_title=session.exam.title,
            remaining_seconds=0,
            elapsed_seconds=session.exam.duration_minutes * 60,
            total_seconds=session.exam.duration_minutes * 60,
            is_expired=True,
            saved_answers={},
            answered_count=len(session.answers),
            total_questions=len(session.exam.questions),
            last_question_id=None,
            can_resume=False,
            message=recovery_status.get("message") or "Ujian sudah selesai dikumpulkan",
            recovery_category=recovery_status.get("category"),
            recovery_message=recovery_status.get("message"),
            session_poll_token=create_session_poll_token(
                session_id=session_id,
                user_id=current_user.id,
                expires_minutes=SESSION_POLL_TOKEN_EXPIRES_MINUTES,
            ),
            session_poll_token_expires_minutes=SESSION_POLL_TOKEN_EXPIRES_MINUTES,
        )

    await db.commit()
    redis_data = await get_session_data(session_id)
    started_at, total_seconds, total_paused = resolve_timer_context(session, redis_data)
    elapsed, remaining = calculate_effective_timer(
        started_at=started_at,
        total_seconds=total_seconds,
        total_paused_seconds=total_paused,
    )
    is_expired = remaining <= 0

    saved_answers: Dict[str, Any] = {}
    last_question_id = None

    redis_answers = await get_session_answers(session_id)
    if redis_answers:
        for key, value in redis_answers.items():
            saved_answers[str(key)] = value

    last_answered_at: Optional[datetime] = None
    for answer in session.answers:
        answer_data: Dict[str, Any] = {}
        if answer.selected_option_id:
            answer_data["selected_option_id"] = answer.selected_option_id
        if answer.selected_option_ids:
            answer_data["selected_option_ids"] = answer.selected_option_ids
        if answer.answer_text:
            answer_data["answer_text"] = answer.answer_text
        answer_meta = answer.answer_metadata or {}
        statement_answers = answer_meta.get("statement_answers")
        if isinstance(statement_answers, dict) and statement_answers:
            answer_data["statement_answers"] = statement_answers

        saved_answers[str(answer.question_id)] = answer_data

        if answer.answered_at and (last_answered_at is None or answer.answered_at > last_answered_at):
            last_answered_at = answer.answered_at
            last_question_id = answer.question_id

    can_resume = bool(recovery_status.get("allow_continue")) and not is_expired

    if is_expired:
        message = "Waktu ujian sudah habis. Jawaban tersimpan otomatis."
    elif can_resume:
        message = f"Lanjutkan ujian. {len(saved_answers)} jawaban tersimpan."
    else:
        message = recovery_status.get("message") or "Sesi tidak dapat dilanjutkan."

    return SessionResumeResponse(
        session_id=session_id,
        exam_id=session.exam.id,
        exam_title=session.exam.title,
        remaining_seconds=remaining,
        elapsed_seconds=elapsed,
        total_seconds=total_seconds,
        is_expired=is_expired,
        saved_answers=saved_answers,
        answered_count=len(saved_answers),
        total_questions=len(session.exam.questions),
        last_question_id=last_question_id,
        can_resume=can_resume,
        message=message,
        recovery_category=recovery_status.get("category"),
        recovery_message=recovery_status.get("message"),
        session_poll_token=create_session_poll_token(
            session_id=session_id,
            user_id=current_user.id,
            expires_minutes=SESSION_POLL_TOKEN_EXPIRES_MINUTES,
        ),
        session_poll_token_expires_minutes=SESSION_POLL_TOKEN_EXPIRES_MINUTES,
    )
