"""Internal answer sync service for legacy-compatible exam answer endpoints.

Phase 5 starts with direct-write behavior. Queue/hybrid Redis buffering can be
introduced behind feature flags after this service boundary is stable.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import sqlalchemy
from fastapi import HTTPException, Request
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exam_answer_validation import (
    get_question_validation_payload_cached,
    validate_answer_with_cached_payload,
)
from app.core.exam_runtime_cache import (
    answer_has_meaningful_content_clause,
    get_exam_question_count_cached,
    invalidate_session_answer_count_cache,
    should_publish_progress_update,
)
from app.core.exam_runtime_state import (
    add_answered_questions_and_count,
    get_answered_count_from_set,
    update_runtime_snapshot_answered_count,
)
from app.core.exam_session_helpers import merge_statement_answer_metadata, safe_int
from app.core.monitoring_delta import publish_monitoring_delta
from app.core.rate_limiter import RateLimiters, check_rate_limit
from app.core.redis_pubsub import (
    get_redis,
    get_session_data,
    publish_message,
    store_session_data,
    update_session_answers,
)
from app.middleware.seb_validation import validate_seb_headers
from app.services.answer_runtime_buffer import (
    AnswerRuntimeBufferService,
    is_runtime_answer_buffer_enabled_for_session,
)
from app.models.question import Question
from app.models.session import Answer, ExamSession
from app.schemas.answer import (
    AnswerJournalAck,
    AnswerJournalSyncRequest,
    AnswerJournalSyncResponse,
    AnswerResponse,
    AnswerSubmit,
    AutoSaveRequest,
    AutoSaveResponse,
)
from app.tasks.answer_processor import enqueue_answer_payload

logger = logging.getLogger(__name__)

SESSION_WRITE_LOCK_NAMESPACE = 48102
ANSWER_JOURNAL_EVENT_TTL_SECONDS = 48 * 60 * 60
ANSWER_JOURNAL_MAX_SYNC_EVENTS = 250
ANSWER_JOURNAL_EVENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9:_-]{8,118}$")


def _answer_journal_event_set_key(session_id: int) -> str:
    return f"exam:answer-journal:v1:session:{session_id}:event-ids"


def _normalize_answer_journal_event_id(raw_event_id: str) -> str:
    return str(raw_event_id or "").strip().lower()


def _is_valid_answer_journal_event_id(event_id: str) -> bool:
    return bool(ANSWER_JOURNAL_EVENT_ID_RE.match(event_id))


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


def _busy_answer_response() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail="Server sedang sibuk, silakan ulangi kirim jawaban.",
        headers={"Retry-After": "1"},
    )


def _already_submitted_answer_response(question_id: int) -> AnswerResponse:
    return AnswerResponse(
        status="saved",
        question_id=question_id,
        message="Sesi ujian sudah dikumpulkan. Jawaban tambahan diabaikan.",
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


async def _acquire_session_write_lock(db: AsyncSession, session_id: int) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :session_id)"),
        {"namespace": SESSION_WRITE_LOCK_NAMESPACE, "session_id": session_id},
    )


async def _ensure_session_in_progress_for_user(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int,
    lock_row: bool = False,
) -> ExamSession:
    query = select(ExamSession).where(
        ExamSession.id == session_id,
        ExamSession.user_id == user_id,
    )
    if lock_row:
        query = query.with_for_update()

    result = await db.execute(query)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")
    if session.status != "in_progress":
        raise HTTPException(status_code=400, detail="Sesi ujian sudah berakhir")
    return session


class AnswerSyncService:
    """Direct-mode answer sync service boundary."""

    def __init__(self, db: AsyncSession, current_user: Any):
        self.db = db
        self.current_user = current_user

    async def accept_single_answer(
        self,
        answer_data: AnswerSubmit,
        request: Request,
    ) -> AnswerResponse:
        """Persist one hot-path answer while preserving the public endpoint contract."""
        await self._check_answer_rate_limit(answer_data.session_id)

        session_probe = await self._probe_single_answer_session(answer_data.session_id)
        if session_probe is None:
            raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

        session_status = str(session_probe["status"] or "").strip().lower()
        if session_status in {"submitted", "completed"}:
            return _already_submitted_answer_response(int(answer_data.question_id))
        if session_status != "in_progress":
            raise HTTPException(status_code=400, detail="Sesi ujian sudah berakhir")

        exam_id = int(session_probe["exam_id"])
        session_id = int(session_probe["id"])
        await self.db.commit()

        await validate_seb_headers(request, exam_id, self.db, require_seb=True)
        question_payload = await self._load_question_validation_payload(
            exam_id=exam_id,
            question_id=int(answer_data.question_id),
        )
        if not question_payload:
            raise HTTPException(status_code=404, detail="Soal tidak ditemukan")

        question_id = int(question_payload["id"])
        final_metadata, statement_answers = self._build_single_answer_metadata(answer_data)
        is_correct, points_earned = self._validate_single_answer(
            question_payload,
            answer_data,
            statement_answers,
        )
        write_timestamp = datetime.now(timezone.utc)
        write_fields = {
            "selected_option_id": answer_data.selected_option_id,
            "selected_option_ids": answer_data.selected_option_ids,
            "answer_text": answer_data.answer_text,
            "answer_metadata": final_metadata,
            "is_correct": is_correct,
            "points_earned": points_earned,
            "answered_at": write_timestamp,
        }

        answered_count_runtime: Optional[int] = None
        try:
            locked_session = await self._lock_session_for_single_answer(session_id, question_id)
            if locked_session is None:
                await self.db.rollback()
                return _already_submitted_answer_response(question_id)

            persisted_via_queue = False
            mode = _answer_write_mode()
            selected_for_async_answer_path = is_runtime_answer_buffer_enabled_for_session(
                session_id=session_id,
                user_id=int(self.current_user.id),
                exam_id=exam_id,
            )
            if mode == "queue" and selected_for_async_answer_path:
                try:
                    await enqueue_answer_payload(
                        {
                            "session_id": session_id,
                            "exam_id": exam_id,
                            "user_id": int(self.current_user.id),
                            "question_id": question_id,
                            "selected_option_id": answer_data.selected_option_id,
                            "selected_option_ids": answer_data.selected_option_ids,
                            "answer_text": answer_data.answer_text,
                            "statement_answers": statement_answers,
                            "answer_metadata": final_metadata,
                            "is_correct": is_correct,
                            "points_earned": points_earned,
                            "answered_at": write_timestamp.isoformat(),
                        }
                    )
                    persisted_via_queue = True
                except Exception as queue_exc:
                    logger.warning(
                        "SUBMIT-ANSWER | session=%s Q%s | queue enqueue failed, fallback direct write: %s",
                        session_id,
                        question_id,
                        str(queue_exc),
                    )

            if mode == "hybrid" and selected_for_async_answer_path:
                await AnswerRuntimeBufferService(self.db, self.current_user).accept_single_answer(
                    session=locked_session,
                    answer_data=answer_data,
                    answer_metadata=final_metadata,
                    is_correct=is_correct,
                    points_earned=points_earned,
                )
                persisted_via_queue = True

            if not persisted_via_queue:
                await self._write_single_answer_direct(
                    session_id=session_id,
                    question_id=question_id,
                    write_fields=write_fields,
                )

            await self.db.commit()
            invalidate_session_answer_count_cache(session_id)
            answered_count_runtime = await self._update_runtime_answered_count(
                session_id,
                [question_id],
                log_prefix="SUBMIT-ANSWER",
            )
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as exc:
            await self.db.rollback()
            if _is_transient_db_pressure_error(exc):
                logger.warning(
                    "SUBMIT-ANSWER | Q%s | transient DB write pressure: %s",
                    question_id,
                    str(exc),
                )
                raise _busy_answer_response()
            logger.error(
                "SUBMIT-ANSWER | Q%s | upsert failed: %s",
                question_id,
                str(exc),
                exc_info=True,
            )
            raise HTTPException(status_code=409, detail="Konflik penyimpanan jawaban, silakan coba lagi")

        try:
            await update_session_answers(session_id, {str(question_id): True})
        except Exception as cache_exc:
            logger.debug(
                "SUBMIT-ANSWER | session=%s | cached answer marker skipped: %s",
                session_id,
                str(cache_exc),
            )
        await self._publish_progress_if_needed(
            session_id=session_id,
            exam_id=exam_id,
            answered_count_runtime=answered_count_runtime,
        )

        return AnswerResponse(
            status="saved",
            question_id=question_id,
            message="Jawaban berhasil disimpan",
        )

    async def _check_answer_rate_limit(self, session_id: int) -> None:
        session_key = f"{self.current_user.id}:{session_id}"
        is_allowed, remaining = await check_rate_limit(RateLimiters.ANSWER_SUBMIT, session_key)
        if not is_allowed:
            raise HTTPException(
                status_code=429,
                detail="Terlalu banyak request. Tunggu beberapa saat.",
                headers={"Retry-After": "5", "X-RateLimit-Remaining": str(remaining)},
            )

    async def _probe_single_answer_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        try:
            session_row_result = await self.db.execute(
                select(
                    ExamSession.id,
                    ExamSession.exam_id,
                    ExamSession.status,
                ).where(
                    ExamSession.id == int(session_id),
                    ExamSession.user_id == self.current_user.id,
                )
            )
        except Exception as exc:
            await self.db.rollback()
            if _is_transient_db_pressure_error(exc):
                logger.warning(
                    "SUBMIT-ANSWER | session=%s | transient DB read pressure: %s",
                    session_id,
                    str(exc),
                )
                raise _busy_answer_response()
            raise

        row = session_row_result.first()
        if row is None:
            return None
        return {"id": int(row[0]), "exam_id": int(row[1]), "status": row[2]}

    async def _load_question_validation_payload(
        self,
        *,
        exam_id: int,
        question_id: int,
    ) -> Optional[Dict[str, Any]]:
        try:
            return await get_question_validation_payload_cached(
                self.db,
                exam_id=exam_id,
                question_id=question_id,
            )
        except Exception as exc:
            if _is_transient_db_pressure_error(exc):
                logger.warning(
                    "SUBMIT-ANSWER | Q%s | transient DB question read pressure: %s",
                    question_id,
                    str(exc),
                )
                raise _busy_answer_response()
            raise

    def _build_single_answer_metadata(
        self,
        answer_data: AnswerSubmit,
    ) -> Tuple[Dict[str, Any], Optional[Dict[str, bool]]]:
        final_metadata, _ = merge_statement_answer_metadata(
            existing_metadata={},
            incoming_metadata=dict(answer_data.answer_metadata or {}),
            incoming_statement_answers=answer_data.statement_answers,
        )
        return final_metadata, answer_data.statement_answers

    def _validate_single_answer(
        self,
        question_payload: Dict[str, Any],
        answer_data: AnswerSubmit,
        statement_answers: Optional[Dict[str, bool]],
    ) -> Tuple[bool, float]:
        question_id = int(question_payload["id"])
        has_answer = (
            answer_data.selected_option_id is not None
            or (answer_data.selected_option_ids is not None and len(answer_data.selected_option_ids) > 0)
            or (answer_data.answer_text is not None and answer_data.answer_text.strip() != "")
            or (statement_answers is not None and len(statement_answers) > 0)
        )
        if not has_answer:
            logger.warning("SUBMIT-ANSWER | Q%s | Tidak ada data jawaban yang valid!", question_id)

        try:
            return validate_answer_with_cached_payload(
                question_payload,
                selected_option_id=answer_data.selected_option_id,
                selected_option_ids=answer_data.selected_option_ids,
                answer_text=answer_data.answer_text,
                statement_answers=statement_answers,
            )
        except Exception as exc:
            logger.error(
                "SUBMIT-ANSWER | Q%s | Error saat validasi: %s",
                question_id,
                str(exc),
                exc_info=True,
            )
            return False, 0.0

    async def _lock_session_for_single_answer(
        self,
        session_id: int,
        question_id: int,
    ) -> Optional[ExamSession]:
        await _acquire_session_write_lock(self.db, session_id)
        result = await self.db.execute(
            select(ExamSession)
            .where(
                ExamSession.id == session_id,
                ExamSession.user_id == self.current_user.id,
            )
            .with_for_update()
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")
        session_status = str(session.status or "").strip().lower()
        if session_status in {"submitted", "completed"}:
            logger.info(
                "SUBMIT-ANSWER | session=%s Q%s | ignored post-submit answer status=%s",
                session_id,
                question_id,
                session_status,
            )
            return None
        if session_status != "in_progress":
            raise HTTPException(status_code=400, detail="Sesi ujian sudah berakhir")
        return session

    async def _write_single_answer_direct(
        self,
        *,
        session_id: int,
        question_id: int,
        write_fields: Dict[str, Any],
    ) -> None:
        # Keep direct answer writes idempotent under autosave/retry bursts.
        # If the same payload is submitted repeatedly, avoid a physical UPDATE
        # (and WAL/row-version churn) while preserving last-answer semantics for
        # real changes. Do not compare answered_at because it changes per retry.
        changed_answer_payload = or_(
            Answer.selected_option_id.is_distinct_from(write_fields["selected_option_id"]),
            Answer.selected_option_ids.is_distinct_from(write_fields["selected_option_ids"]),
            Answer.answer_text.is_distinct_from(write_fields["answer_text"]),
            Answer.answer_metadata.is_distinct_from(write_fields["answer_metadata"]),
            Answer.is_correct.is_distinct_from(write_fields["is_correct"]),
            Answer.points_earned.is_distinct_from(write_fields["points_earned"]),
        )
        upsert_stmt = (
            pg_insert(Answer)
            .values(
                session_id=session_id,
                question_id=question_id,
                **write_fields,
            )
            .on_conflict_do_update(
                index_elements=[Answer.session_id, Answer.question_id],
                set_=write_fields,
                where=changed_answer_payload,
            )
        )
        try:
            await self.db.execute(upsert_stmt)
        except sqlalchemy.exc.DBAPIError as upsert_exc:
            if "no unique or exclusion constraint" not in str(upsert_exc).lower():
                raise
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(:session_id, :question_id)"),
                {"session_id": session_id, "question_id": question_id},
            )
            update_stmt = (
                update(Answer)
                .where(
                    Answer.session_id == session_id,
                    Answer.question_id == question_id,
                )
                .values(**write_fields)
            )
            update_result = await self.db.execute(update_stmt)
            if (update_result.rowcount or 0) == 0:
                self.db.add(
                    Answer(
                        session_id=session_id,
                        question_id=question_id,
                        **write_fields,
                    )
                )

    async def _publish_progress_if_needed(
        self,
        *,
        session_id: int,
        exam_id: int,
        answered_count_runtime: Optional[int],
    ) -> None:
        if bool(getattr(settings, "exam_peak_mode", False)):
            logger.debug(
                "SUBMIT-ANSWER | session=%s | progress broadcast skipped during peak mode",
                session_id,
            )
            return
        if not should_publish_progress_update(session_id):
            return
        try:
            answered_count: Optional[int] = answered_count_runtime
            if answered_count is None:
                try:
                    answered_count = await get_answered_count_from_set(session_id)
                except Exception as runtime_exc:
                    logger.debug(
                        "SUBMIT-ANSWER | session=%s | failed reading answered_count set: %s",
                        session_id,
                        str(runtime_exc),
                    )
            if answered_count is None:
                if bool(getattr(settings, "exam_peak_mode", False)):
                    logger.debug(
                        "SUBMIT-ANSWER | session=%s | progress DB fallback skipped during peak mode",
                        session_id,
                    )
                    return
                answered_result = await self.db.execute(
                    select(func.count(func.distinct(Answer.question_id))).where(
                        Answer.session_id == session_id,
                        answer_has_meaningful_content_clause(),
                    )
                )
                answered_count = int(answered_result.scalar() or 0)
            total_questions = await get_exam_question_count_cached(self.db, exam_id)
            progress = (answered_count / total_questions * 100) if total_questions > 0 else 0.0
            await self.db.commit()
            await _publish_exam_monitor_event(
                exam_id,
                {
                    "type": "progress_update",
                    "user_id": self.current_user.id,
                    "exam_id": exam_id,
                    "session_id": session_id,
                    "progress": round(progress, 2),
                    "answered_count": answered_count,
                    "total_questions": total_questions,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            logger.warning(
                "SUBMIT-ANSWER | session=%s | progress broadcast skipped: %s",
                session_id,
                str(exc),
            )

    async def accept_legacy_autosave(self, save_data: AutoSaveRequest) -> AutoSaveResponse:
        """Handle legacy autosave cache updates without direct answer writes."""
        result = await self.db.execute(
            select(ExamSession).where(
                ExamSession.id == save_data.session_id,
                ExamSession.user_id == self.current_user.id,
                ExamSession.status == "in_progress",
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan atau sudah berakhir")

        await update_session_answers(session.id, save_data.answers)
        try:
            answered_count_runtime = await add_answered_questions_and_count(
                session.id,
                list((save_data.answers or {}).keys()),
            )
            if answered_count_runtime is not None:
                await update_runtime_snapshot_answered_count(
                    session.id,
                    expected_user_id=self.current_user.id,
                    answered_count=answered_count_runtime,
                    mark_stale=False,
                    status="in_progress",
                )
        except Exception as runtime_exc:
            logger.debug(
                "AUTO-SAVE | session=%s | runtime answered_count update skipped: %s",
                session.id,
                str(runtime_exc),
            )

        return AutoSaveResponse(
            status="success",
            saved_count=len(save_data.answers),
            timestamp=datetime.now(timezone.utc),
        )

    async def accept_batch(self, batch_data: Any) -> Dict[str, Any]:
        """Persist batch autosave in direct DB mode with no-op update skip."""
        result = await self.db.execute(
            select(ExamSession).where(
                ExamSession.id == batch_data.session_id,
                ExamSession.user_id == self.current_user.id,
                ExamSession.status == "in_progress",
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan atau sudah berakhir")

        if is_runtime_answer_buffer_enabled_for_session(
            session_id=int(session.id),
            user_id=int(self.current_user.id),
            exam_id=int(session.exam_id),
        ):
            return await AnswerRuntimeBufferService(self.db, self.current_user).accept_batch(batch_data)

        if not batch_data.answers:
            return {
                "status": "no_changes",
                "queued_count": 0,
                "queue_id": "empty",
                "timestamp": datetime.now(timezone.utc),
            }

        queue_id = str(uuid.uuid4())[:8]
        deduped_answer_map: Dict[int, Any] = {}
        for item in batch_data.answers:
            deduped_answer_map[int(item.question_id)] = item

        deduped_answers = list(deduped_answer_map.values())
        question_ids = [int(answer.question_id) for answer in deduped_answers]
        valid_question_ids: Set[int] = set()
        if question_ids:
            valid_question_result = await self.db.execute(
                select(Question.id).where(
                    Question.exam_id == session.exam_id,
                    Question.id.in_(question_ids),
                )
            )
            valid_question_ids = {int(row[0]) for row in valid_question_result.all()}

        session_id_value = int(session.id)
        if question_ids and len(valid_question_ids) != len(set(question_ids)):
            dropped_count = len(set(question_ids)) - len(valid_question_ids)
            logger.warning(
                "AUTO-SAVE-BATCH | Session %s | dropped %s invalid question_id(s)",
                session_id_value,
                dropped_count,
            )

        valid_answers = [a for a in deduped_answers if int(a.question_id) in valid_question_ids]

        await _acquire_session_write_lock(self.db, session_id_value)
        session = await _ensure_session_in_progress_for_user(
            self.db,
            session_id=session_id_value,
            user_id=self.current_user.id,
            lock_row=True,
        )
        session_id_value = int(session.id)

        existing_answer_map: Dict[int, Answer] = {}
        if valid_question_ids:
            existing_result = await self.db.execute(
                select(Answer).where(
                    Answer.session_id == session_id_value,
                    Answer.question_id.in_(valid_question_ids),
                )
            )
            existing_answer_map = {
                int(answer.question_id): answer for answer in existing_result.scalars().all()
            }

        now_utc = datetime.now(timezone.utc)
        changed_rows = 0
        for answer_data in valid_answers:
            question_id = int(answer_data.question_id)
            existing_answer = existing_answer_map.get(question_id)
            incoming_metadata = dict(answer_data.answer_metadata or {})
            existing_metadata = dict(existing_answer.answer_metadata or {}) if existing_answer else {}
            final_metadata, _ = merge_statement_answer_metadata(
                existing_metadata=existing_metadata,
                incoming_metadata=incoming_metadata,
                incoming_statement_answers=answer_data.statement_answers,
            )

            if existing_answer:
                has_changed = (
                    existing_answer.selected_option_id != answer_data.selected_option_id
                    or existing_answer.selected_option_ids != answer_data.selected_option_ids
                    or existing_answer.answer_text != answer_data.answer_text
                    or dict(existing_answer.answer_metadata or {}) != final_metadata
                )
                if has_changed:
                    existing_answer.selected_option_id = answer_data.selected_option_id
                    existing_answer.selected_option_ids = answer_data.selected_option_ids
                    existing_answer.answer_text = answer_data.answer_text
                    existing_answer.answer_metadata = final_metadata
                    existing_answer.answered_at = now_utc
                    existing_answer.is_correct = None
                    existing_answer.points_earned = None
                    changed_rows += 1
            else:
                self.db.add(
                    Answer(
                        session_id=session_id_value,
                        question_id=question_id,
                        selected_option_id=answer_data.selected_option_id,
                        selected_option_ids=answer_data.selected_option_ids,
                        answer_text=answer_data.answer_text,
                        answer_metadata=final_metadata,
                        answered_at=now_utc,
                        is_correct=None,
                        points_earned=None,
                    )
                )
                changed_rows += 1

        if changed_rows > 0:
            try:
                await self.db.commit()
                invalidate_session_answer_count_cache(session_id_value)
            except Exception as integrity_error:
                logger.warning(
                    "AUTO-SAVE-BATCH | Session %s | write conflict, retrying serialized merge: %s",
                    session_id_value,
                    str(integrity_error),
                )
                await self.db.rollback()
                await self._retry_batch_serialized(session_id_value, valid_answers)
                changed_rows = max(changed_rows, len(valid_answers))

        await update_session_answers(session_id_value, {str(a.question_id): True for a in valid_answers})
        await self._update_runtime_answered_count(
            session_id_value,
            [int(a.question_id) for a in valid_answers],
            log_prefix="AUTO-SAVE-BATCH",
        )

        return {
            "status": "saved_to_db" if changed_rows > 0 else "no_changes",
            "queued_count": len(valid_answers),
            "queue_id": queue_id,
            "timestamp": datetime.now(timezone.utc),
        }

    async def _retry_batch_serialized(self, session_id_value: int, valid_answers: List[Any]) -> None:
        await _acquire_session_write_lock(self.db, session_id_value)
        await _ensure_session_in_progress_for_user(
            self.db,
            session_id=session_id_value,
            user_id=self.current_user.id,
            lock_row=True,
        )
        fallback_timestamp = datetime.now(timezone.utc)
        for answer_data in valid_answers:
            incoming_metadata = dict(answer_data.answer_metadata or {})
            retry_existing_result = await self.db.execute(
                select(Answer)
                .where(
                    Answer.session_id == session_id_value,
                    Answer.question_id == int(answer_data.question_id),
                )
                .with_for_update()
            )
            retry_existing_answer = retry_existing_result.scalar_one_or_none()
            retry_existing_metadata = (
                dict(retry_existing_answer.answer_metadata or {})
                if retry_existing_answer
                else {}
            )
            retry_metadata, _ = merge_statement_answer_metadata(
                existing_metadata=retry_existing_metadata,
                incoming_metadata=incoming_metadata,
                incoming_statement_answers=answer_data.statement_answers,
            )
            if retry_existing_answer:
                retry_existing_answer.selected_option_id = answer_data.selected_option_id
                retry_existing_answer.selected_option_ids = answer_data.selected_option_ids
                retry_existing_answer.answer_text = answer_data.answer_text
                retry_existing_answer.answer_metadata = retry_metadata
                retry_existing_answer.answered_at = fallback_timestamp
                retry_existing_answer.is_correct = None
                retry_existing_answer.points_earned = None
            else:
                self.db.add(
                    Answer(
                        session_id=session_id_value,
                        question_id=int(answer_data.question_id),
                        selected_option_id=answer_data.selected_option_id,
                        selected_option_ids=answer_data.selected_option_ids,
                        answer_text=answer_data.answer_text,
                        answer_metadata=retry_metadata,
                        answered_at=fallback_timestamp,
                        is_correct=None,
                        points_earned=None,
                    )
                )
        await self.db.commit()
        invalidate_session_answer_count_cache(session_id_value)

    async def accept_journal_events(
        self,
        sync_data: AnswerJournalSyncRequest,
    ) -> AnswerJournalSyncResponse:
        """Apply idempotent answer journal events in one transaction."""
        if len(sync_data.events) > ANSWER_JOURNAL_MAX_SYNC_EVENTS:
            raise HTTPException(
                status_code=422,
                detail=f"Maksimal {ANSWER_JOURNAL_MAX_SYNC_EVENTS} event per sinkronisasi",
            )

        result = await self.db.execute(
            select(ExamSession).where(
                ExamSession.id == sync_data.session_id,
                ExamSession.user_id == self.current_user.id,
                ExamSession.status.in_(["in_progress", "active"]),
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan atau tidak aktif")

        if not sync_data.events:
            return AnswerJournalSyncResponse(
                status="ok",
                accepted=0,
                duplicates=0,
                invalid=0,
                applied_question_count=0,
                acks=[],
                server_time=datetime.now(timezone.utc),
            )

        requested_question_ids = {int(event.question_id) for event in sync_data.events}
        valid_question_result = await self.db.execute(
            select(Question.id).where(
                Question.exam_id == session.exam_id,
                Question.id.in_(requested_question_ids),
            )
        )
        valid_question_ids = {int(row[0]) for row in valid_question_result.all()}

        redis = await get_redis()
        session_id_value = int(session.id)
        event_set_key = _answer_journal_event_set_key(session_id_value)
        normalized_event_ids = [
            _normalize_answer_journal_event_id(event.event_id) for event in sync_data.events
        ]
        existing_event_ids = await self._read_existing_journal_event_ids(
            redis,
            event_set_key,
            normalized_event_ids,
            session_id_value,
        )

        accepted_events, acks, duplicate_count, invalid_count = self._classify_journal_events(
            sync_data,
            valid_question_ids,
            existing_event_ids,
        )
        if not accepted_events:
            return AnswerJournalSyncResponse(
                status="ok",
                accepted=0,
                duplicates=duplicate_count,
                invalid=invalid_count,
                applied_question_count=0,
                acks=acks,
                server_time=datetime.now(timezone.utc),
            )

        if is_runtime_answer_buffer_enabled_for_session(
            session_id=session_id_value,
            user_id=int(self.current_user.id),
            exam_id=int(session.exam_id),
        ):
            buffered_count = await AnswerRuntimeBufferService(
                self.db,
                self.current_user,
            ).accept_journal_events(sync_data, accepted_events)
            accepted_event_ids = [event_id for event_id, _ in accepted_events]
            if accepted_event_ids:
                await redis.sadd(event_set_key, *accepted_event_ids)
                await redis.expire(event_set_key, ANSWER_JOURNAL_EVENT_TTL_SECONDS)
            for event_id, event in accepted_events:
                acks.append(
                    AnswerJournalAck(
                        event_id=event_id,
                        question_id=int(event.question_id),
                        status="applied",
                    )
                )
            return AnswerJournalSyncResponse(
                status="ok",
                accepted=len(accepted_events),
                duplicates=duplicate_count,
                invalid=invalid_count,
                applied_question_count=buffered_count,
                acks=acks,
                server_time=datetime.now(timezone.utc),
            )

        latest_by_question = self._latest_journal_events_by_question(accepted_events)
        await _acquire_session_write_lock(self.db, session_id_value)
        session = await _ensure_session_in_progress_for_user(
            self.db,
            session_id=session_id_value,
            user_id=self.current_user.id,
            lock_row=True,
        )
        session_id_value = int(session.id)

        question_ids_to_apply = list(latest_by_question.keys())
        existing_answer_map = await self._load_existing_answers(session_id_value, question_ids_to_apply)
        changed_rows = self._apply_journal_answers(
            session_id_value,
            latest_by_question,
            existing_answer_map,
        )

        if changed_rows > 0:
            await self.db.commit()
            invalidate_session_answer_count_cache(session_id_value)
        else:
            await self.db.rollback()

        try:
            accepted_event_ids = [event_id for event_id, _ in accepted_events]
            if accepted_event_ids:
                await redis.sadd(event_set_key, *accepted_event_ids)
                await redis.expire(event_set_key, ANSWER_JOURNAL_EVENT_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                "ANSWER-JOURNAL | Session %s | failed writing idempotency set: %s",
                session_id_value,
                str(exc),
            )

        await update_session_answers(
            session_id_value,
            {str(question_id): True for question_id in question_ids_to_apply},
        )
        await self._update_runtime_answered_count(
            session_id_value,
            question_ids_to_apply,
            log_prefix="ANSWER-JOURNAL",
        )

        for event_id, event in accepted_events:
            acks.append(
                AnswerJournalAck(
                    event_id=event_id,
                    question_id=int(event.question_id),
                    status="applied",
                )
            )

        return AnswerJournalSyncResponse(
            status="ok",
            accepted=len(accepted_events),
            duplicates=duplicate_count,
            invalid=invalid_count,
            applied_question_count=len(question_ids_to_apply),
            acks=acks,
            server_time=datetime.now(timezone.utc),
        )

    async def _read_existing_journal_event_ids(
        self,
        redis: Any,
        event_set_key: str,
        normalized_event_ids: List[str],
        session_id_value: int,
    ) -> Set[str]:
        existing_event_ids: Set[str] = set()
        try:
            if normalized_event_ids:
                pipeline = redis.pipeline()
                for event_id in normalized_event_ids:
                    pipeline.sismember(event_set_key, event_id)
                existing_flags = await pipeline.execute()
                existing_event_ids = {
                    event_id
                    for event_id, flag in zip(normalized_event_ids, existing_flags)
                    if bool(flag)
                }
        except Exception as exc:
            logger.warning(
                "ANSWER-JOURNAL | Session %s | failed checking Redis idempotency set: %s",
                session_id_value,
                str(exc),
            )
        return existing_event_ids

    def _classify_journal_events(
        self,
        sync_data: AnswerJournalSyncRequest,
        valid_question_ids: Set[int],
        existing_event_ids: Set[str],
    ) -> Tuple[List[Tuple[str, Any]], List[AnswerJournalAck], int, int]:
        ordered_events = sorted(
            sync_data.events,
            key=lambda item: (int(item.sequence), int(item.local_timestamp_ms)),
        )
        seen_in_payload: Set[str] = set()
        accepted_events: List[Tuple[str, Any]] = []
        acks: List[AnswerJournalAck] = []
        duplicate_count = 0
        invalid_count = 0

        for event in ordered_events:
            event_id = _normalize_answer_journal_event_id(event.event_id)
            question_id = int(event.question_id)
            if not _is_valid_answer_journal_event_id(event_id):
                invalid_count += 1
                acks.append(AnswerJournalAck(event_id=event_id, question_id=question_id, status="invalid", reason="invalid_event_id"))
                continue
            if event_id in seen_in_payload:
                duplicate_count += 1
                acks.append(AnswerJournalAck(event_id=event_id, question_id=question_id, status="duplicate", reason="duplicate_in_payload"))
                continue
            seen_in_payload.add(event_id)
            if question_id not in valid_question_ids:
                invalid_count += 1
                acks.append(AnswerJournalAck(event_id=event_id, question_id=question_id, status="invalid", reason="invalid_question_id"))
                continue
            if event_id in existing_event_ids:
                duplicate_count += 1
                acks.append(AnswerJournalAck(event_id=event_id, question_id=question_id, status="duplicate", reason="already_acked"))
                continue
            accepted_events.append((event_id, event))
        return accepted_events, acks, duplicate_count, invalid_count

    def _latest_journal_events_by_question(self, accepted_events: List[Tuple[str, Any]]) -> Dict[int, Tuple[str, Any]]:
        latest_by_question: Dict[int, Tuple[str, Any]] = {}
        for event_id, event in accepted_events:
            question_id = int(event.question_id)
            current = latest_by_question.get(question_id)
            if current is None:
                latest_by_question[question_id] = (event_id, event)
                continue
            _, current_event = current
            if (int(event.sequence), int(event.local_timestamp_ms)) >= (
                int(current_event.sequence),
                int(current_event.local_timestamp_ms),
            ):
                latest_by_question[question_id] = (event_id, event)
        return latest_by_question

    async def _load_existing_answers(self, session_id_value: int, question_ids: List[int]) -> Dict[int, Answer]:
        if not question_ids:
            return {}
        existing_result = await self.db.execute(
            select(Answer).where(
                Answer.session_id == session_id_value,
                Answer.question_id.in_(question_ids),
            )
        )
        return {int(answer.question_id): answer for answer in existing_result.scalars().all()}

    def _apply_journal_answers(
        self,
        session_id_value: int,
        latest_by_question: Dict[int, Tuple[str, Any]],
        existing_answer_map: Dict[int, Answer],
    ) -> int:
        now_utc = datetime.now(timezone.utc)
        changed_rows = 0
        for question_id, (event_id, event) in latest_by_question.items():
            existing_answer = existing_answer_map.get(question_id)
            incoming_metadata = dict(event.answer_metadata or {})
            incoming_metadata["client_event_id"] = event_id
            incoming_metadata["client_sequence"] = int(event.sequence)
            incoming_metadata["client_local_timestamp_ms"] = int(event.local_timestamp_ms)
            incoming_metadata["sync_source"] = "answer_journal_v1"
            existing_metadata = dict(existing_answer.answer_metadata or {}) if existing_answer else {}
            final_metadata, _ = merge_statement_answer_metadata(
                existing_metadata=existing_metadata,
                incoming_metadata=incoming_metadata,
                incoming_statement_answers=event.statement_answers,
            )
            if existing_answer:
                has_changed = (
                    existing_answer.selected_option_id != event.selected_option_id
                    or existing_answer.selected_option_ids != event.selected_option_ids
                    or existing_answer.answer_text != event.answer_text
                    or dict(existing_answer.answer_metadata or {}) != final_metadata
                )
                if not has_changed:
                    continue
                existing_answer.selected_option_id = event.selected_option_id
                existing_answer.selected_option_ids = event.selected_option_ids
                existing_answer.answer_text = event.answer_text
                existing_answer.answer_metadata = final_metadata
                existing_answer.answered_at = now_utc
                existing_answer.is_correct = None
                existing_answer.points_earned = None
                changed_rows += 1
            else:
                self.db.add(
                    Answer(
                        session_id=session_id_value,
                        question_id=question_id,
                        selected_option_id=event.selected_option_id,
                        selected_option_ids=event.selected_option_ids,
                        answer_text=event.answer_text,
                        answer_metadata=final_metadata,
                        answered_at=now_utc,
                        is_correct=None,
                        points_earned=None,
                    )
                )
                changed_rows += 1
        return changed_rows

    async def _update_runtime_answered_count(
        self,
        session_id_value: int,
        question_ids: List[int],
        *,
        log_prefix: str,
    ) -> Optional[int]:
        try:
            answered_count_runtime = await add_answered_questions_and_count(
                session_id_value,
                question_ids,
            )
            if answered_count_runtime is not None:
                await update_runtime_snapshot_answered_count(
                    session_id_value,
                    expected_user_id=self.current_user.id,
                    answered_count=answered_count_runtime,
                    mark_stale=False,
                    status="in_progress",
                )
                return int(answered_count_runtime)
            cached_session_data = await get_session_data(session_id_value)
            if cached_session_data and safe_int(cached_session_data.get("user_id")) == self.current_user.id:
                cached_session_data["answered_count_stale"] = True
                await store_session_data(session_id_value, cached_session_data)
        except Exception as runtime_exc:
            logger.debug(
                "%s | session=%s | runtime answered_count update skipped: %s",
                log_prefix,
                session_id_value,
                str(runtime_exc),
            )
        return None


def get_answer_sync_service(db: AsyncSession, current_user: Any) -> AnswerSyncService:
    return AnswerSyncService(db=db, current_user=current_user)
