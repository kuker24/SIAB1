"""Priority final-submit orchestration for exam sessions.

Final submit is the highest-priority student write path. It must not be blocked
by non-critical monitoring/violation features and, when answer buffering is
enabled, must synchronously flush the submitting session before grading.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import sqlalchemy
from fastapi import HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload, selectinload

from app.config import settings
from app.core.exam_results_cache import invalidate_exam_results_cache
from app.core.exam_session_helpers import safe_int
from app.core.monitoring_delta import publish_monitoring_delta
from app.core.rate_limiter import RateLimiters, check_rate_limit
from app.core.redis_pubsub import get_session_data, publish_message, store_session_data
from app.middleware.seb_validation import validate_seb_headers
from app.models.exam import Exam
from app.models.question import Question
from app.models.session import ExamLog, ExamSession
from app.schemas.answer import ExamSubmitRequest, ExamSubmitResponse
from app.services.answer_runtime_buffer import (
    flush_runtime_answer_buffer_for_session,
    is_runtime_answer_buffer_enabled,
)
from app.services.exam_submission_service import finalize_exam_session_submission
from app.tasks.answer_processor import drain_answer_queue

logger = logging.getLogger(__name__)

SESSION_WRITE_LOCK_NAMESPACE = 48102


async def _acquire_session_write_lock(db: AsyncSession, session_id: int) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :session_id)"),
        {"namespace": SESSION_WRITE_LOCK_NAMESPACE, "session_id": session_id},
    )


async def _publish_exam_monitor_event(exam_id: int, payload: Dict[str, Any]) -> None:
    await publish_message(f"exam_monitor_{exam_id}", payload)
    try:
        await publish_monitoring_delta(
            exam_id=exam_id,
            event_type=str(payload.get("type") or "event"),
            payload=payload,
        )
    except Exception as delta_exc:
        logger.debug("Failed to mirror monitor event to delta stream: %s", str(delta_exc))


def _answer_write_mode() -> str:
    mode = str(getattr(settings, "answer_write_mode", "direct") or "direct").strip().lower()
    if mode in {"queue", "hybrid"}:
        return mode
    return "direct"


def _is_transient_db_pressure_error(exc: Exception) -> bool:
    if isinstance(exc, sqlalchemy.exc.TimeoutError):
        return True
    if isinstance(exc, sqlalchemy.exc.DBAPIError):
        if bool(getattr(exc, "connection_invalidated", False)):
            return True
        message = str(exc).lower()
        transient_markers = (
            "queuepool limit",
            "connection was closed in the middle of operation",
            "too many clients already",
            "canceling statement due to statement timeout",
            "could not serialize access due to concurrent update",
        )
        return any(marker in message for marker in transient_markers)
    return False


def _build_already_submitted_response(
    *,
    session_id: int,
    score: Optional[float],
    show_results: Optional[bool],
    passing_score: Optional[float],
) -> ExamSubmitResponse:
    resolved_show_results = show_results if show_results is not None else True
    passed = None
    if resolved_show_results and score is not None and passing_score is not None:
        passed = float(score) >= float(passing_score)
    return ExamSubmitResponse(
        session_id=session_id,
        status="submitted",
        score=float(score) if resolved_show_results and score is not None else None,
        total_points=None,
        points_earned=None,
        percentage=float(score) if resolved_show_results and score is not None else None,
        passed=passed if resolved_show_results else None,
        message="Sesi sudah pernah dikumpulkan.",
    )


class FinalSubmitService:
    """Service boundary for student final submit."""

    def __init__(self, db: AsyncSession, current_user: Any):
        self.db = db
        self.current_user = current_user

    async def submit_exam(self, submit_data: ExamSubmitRequest, request: Request) -> ExamSubmitResponse:
        """Submit entire exam with answer-flush priority and idempotent retry handling."""
        await self._check_submit_rate_limit()
        session_probe = await self._probe_session_state(submit_data.session_id)

        if session_probe is None:
            raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

        if session_probe["status"] in {"submitted", "completed"}:
            return _build_already_submitted_response(
                session_id=int(session_probe["session_id"]),
                score=(
                    float(session_probe["score"])
                    if session_probe["score"] is not None
                    else None
                ),
                show_results=(
                    bool(session_probe["show_results"])
                    if session_probe["show_results"] is not None
                    else None
                ),
                passing_score=(
                    float(session_probe["passing_score"])
                    if session_probe["passing_score"] is not None
                    else None
                ),
            )

        if session_probe["status"] != "in_progress":
            raise HTTPException(status_code=400, detail="Sesi ujian sudah berakhir")

        # Release probe transaction before SEB/network work.
        await self.db.commit()

        await validate_seb_headers(request, int(session_probe["exam_id"]), self.db, require_seb=True)
        await self._flush_answer_buffers_before_submit(int(submit_data.session_id))

        session = await self._load_session_for_finalize(submit_data.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

        if session.status in {"submitted", "completed"}:
            return _build_already_submitted_response(
                session_id=session.id,
                score=float(session.score) if session.score is not None else None,
                show_results=(
                    bool(session.exam.show_results)
                    if session.exam.show_results is not None
                    else None
                ),
                passing_score=(
                    float(session.exam.passing_score)
                    if session.exam.passing_score is not None
                    else None
                ),
            )

        if session.status != "in_progress":
            raise HTTPException(status_code=400, detail="Sesi ujian sudah berakhir")

        finalize_result = await self._finalize_and_commit(session, submit_data)
        await self._after_submit_best_effort(session, finalize_result.percentage)

        passed = None
        if session.exam.passing_score:
            passed = finalize_result.percentage >= float(session.exam.passing_score)

        show_results = session.exam.show_results if session.exam.show_results is not None else True
        return ExamSubmitResponse(
            session_id=session.id,
            status="submitted",
            score=finalize_result.percentage if show_results else None,
            total_points=finalize_result.total_points if show_results else None,
            points_earned=finalize_result.points_earned if show_results else None,
            percentage=finalize_result.percentage if show_results else None,
            passed=passed if show_results else None,
            message=(
                "Ujian berhasil dikumpulkan"
                if not submit_data.force_submit
                else "Ujian dikumpulkan otomatis karena pelanggaran"
            ),
        )

    async def _check_submit_rate_limit(self) -> None:
        is_allowed, remaining = await check_rate_limit(
            RateLimiters.EXAM_SUBMIT,
            str(self.current_user.id),
        )
        if not is_allowed:
            raise HTTPException(
                status_code=429,
                detail="Terlalu banyak percobaan submit. Tunggu beberapa saat.",
                headers={"Retry-After": "20", "X-RateLimit-Remaining": str(remaining)},
            )

    async def _probe_session_state(self, session_id: int) -> Optional[Dict[str, Any]]:
        try:
            probe_result = await self.db.execute(
                select(
                    ExamSession.id.label("session_id"),
                    ExamSession.exam_id.label("exam_id"),
                    ExamSession.status.label("status"),
                    ExamSession.score.label("score"),
                    Exam.show_results.label("show_results"),
                    Exam.passing_score.label("passing_score"),
                )
                .join(Exam, Exam.id == ExamSession.exam_id)
                .where(
                    ExamSession.id == session_id,
                    ExamSession.user_id == self.current_user.id,
                )
            )
        except Exception as exc:
            await self.db.rollback()
            if _is_transient_db_pressure_error(exc):
                logger.warning(
                    "SUBMIT-EXAM | session=%s | transient DB probe pressure: %s",
                    session_id,
                    str(exc),
                )
                raise HTTPException(
                    status_code=503,
                    detail="Server sedang sibuk, silakan ulangi submit.",
                    headers={"Retry-After": "1"},
                )
            raise
        row = probe_result.mappings().one_or_none()
        return dict(row) if row is not None else None

    async def _flush_answer_buffers_before_submit(self, session_id: int) -> None:
        if _answer_write_mode() == "queue" and settings.answer_queue_flush_on_submit:
            try:
                drained = await drain_answer_queue(
                    max_rounds=max(1, int(settings.answer_queue_flush_max_rounds)),
                    batch_size=max(1, int(settings.answer_queue_flush_batch_size)),
                )
                if drained > 0:
                    logger.info(
                        "SUBMIT-EXAM | session=%s | legacy queue pre-flush processed=%s",
                        session_id,
                        drained,
                    )
            except Exception as queue_flush_exc:
                logger.warning(
                    "SUBMIT-EXAM | session=%s | legacy queue pre-flush failed (continue): %s",
                    session_id,
                    str(queue_flush_exc),
                )

        if is_runtime_answer_buffer_enabled():
            try:
                flushed = await flush_runtime_answer_buffer_for_session(self.db, session_id)
                if flushed > 0:
                    logger.info(
                        "SUBMIT-EXAM | session=%s | runtime buffer pre-flush rows=%s",
                        session_id,
                        flushed,
                    )
            except Exception as runtime_flush_exc:
                await self.db.rollback()
                logger.warning(
                    "SUBMIT-EXAM | session=%s | runtime buffer pre-flush failed: %s",
                    session_id,
                    str(runtime_flush_exc),
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Server sedang menyimpan jawaban terakhir, silakan ulangi submit.",
                    headers={"Retry-After": "1"},
                )

    async def _load_session_for_finalize(self, session_id: int) -> Optional[ExamSession]:
        try:
            await _acquire_session_write_lock(self.db, session_id)
            result = await self.db.execute(
                select(ExamSession)
                .options(
                    noload("*"),
                    selectinload(ExamSession.exam).options(
                        noload("*"),
                        selectinload(Exam.questions).options(
                            noload("*"),
                            selectinload(Question.options).options(noload("*")),
                        ),
                    ),
                    selectinload(ExamSession.answers).options(noload("*")),
                )
                .where(
                    ExamSession.id == session_id,
                    ExamSession.user_id == self.current_user.id,
                )
                .with_for_update()
            )
            return result.scalar_one_or_none()
        except Exception as exc:
            await self.db.rollback()
            if _is_transient_db_pressure_error(exc):
                logger.warning(
                    "SUBMIT-EXAM | session=%s | transient DB lock/load pressure: %s",
                    session_id,
                    str(exc),
                )
                raise HTTPException(
                    status_code=503,
                    detail="Server sedang sibuk, silakan ulangi submit.",
                    headers={"Retry-After": "1"},
                )
            raise

    async def _finalize_and_commit(self, session: ExamSession, submit_data: ExamSubmitRequest) -> Any:
        try:
            finalize_result = finalize_exam_session_submission(
                session,
                submitted_at=datetime.now(timezone.utc),
            )
            self.db.add(
                ExamLog(
                    session_id=session.id,
                    event_type="EXAM_SUBMITTED",
                    event_data={
                        "force_submit": submit_data.force_submit,
                        "recovery_category": (
                            "cheating_detected" if submit_data.force_submit else "session_submitted"
                        ),
                        "score": finalize_result.percentage,
                        "violation_count": session.violation_count,
                    },
                )
            )
            self.db.add(
                ExamLog(
                    session_id=session.id,
                    event_type="SCORE_BREAKDOWN",
                    event_data={"score_breakdown": finalize_result.score_breakdown},
                )
            )
            await self.db.commit()
            return finalize_result
        except Exception as exc:
            await self.db.rollback()
            if _is_transient_db_pressure_error(exc):
                logger.warning(
                    "SUBMIT-EXAM | session=%s | transient DB finalize pressure: %s",
                    session.id,
                    str(exc),
                )
                raise HTTPException(
                    status_code=503,
                    detail="Server sedang sibuk, silakan ulangi submit.",
                    headers={"Retry-After": "1"},
                )
            logger.error(
                "SUBMIT-EXAM | session=%s | finalize failed: %s",
                session.id,
                str(exc),
                exc_info=True,
            )
            raise HTTPException(status_code=500, detail="Gagal mengumpulkan ujian")

    async def _after_submit_best_effort(self, session: ExamSession, percentage: float) -> None:
        try:
            await invalidate_exam_results_cache(session.exam_id)
        except Exception as cache_invalidate_exc:
            logger.debug(
                "SUBMIT-EXAM | session=%s | failed to invalidate result cache: %s",
                session.id,
                str(cache_invalidate_exc),
            )

        try:
            cached_session_data = await get_session_data(session.id)
            if cached_session_data and safe_int(cached_session_data.get("user_id")) == self.current_user.id:
                cached_session_data["session_id"] = session.id
                cached_session_data["exam_id"] = session.exam_id
                cached_session_data["status"] = "submitted"
                cached_session_data["end_time"] = session.end_time.isoformat() if session.end_time else None
                cached_session_data["answered_count_stale"] = False
                cached_session_data["violation_count"] = int(session.violation_count or 0)
                await store_session_data(session.id, cached_session_data)
        except Exception as cache_exc:
            logger.debug(
                "SUBMIT-EXAM | session=%s | failed to persist redis submit state: %s",
                session.id,
                str(cache_exc),
            )

        try:
            await _publish_exam_monitor_event(
                session.exam_id,
                {
                    "type": "student_submitted",
                    "user_id": self.current_user.id,
                    "username": self.current_user.username,
                    "session_id": session.id,
                    "score": percentage,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            logger.warning("Failed to publish submission event for session %s: %s", session.id, str(exc))


def get_final_submit_service(db: AsyncSession, current_user: Any) -> FinalSubmitService:
    return FinalSubmitService(db, current_user)
