"""Redis runtime buffer for autosave/journal answer writes.

Phase 6 implementation is feature-flagged and disabled by default. It stores the
latest answer per question in Redis, tracks dirty questions, and lets a
background drainer flush batches into PostgreSQL.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exam_runtime_cache import invalidate_session_answer_count_cache
from app.core.exam_runtime_state import (
    add_answered_questions_and_count,
    update_runtime_snapshot_answered_count,
)
from app.core.exam_session_helpers import merge_statement_answer_metadata
from app.core.redis_pubsub import get_redis, update_session_answers
from app.database import async_session_write
from app.models.question import Question
from app.models.session import Answer, ExamSession

logger = logging.getLogger(__name__)

SESSION_WRITE_LOCK_NAMESPACE = 48102
RUNTIME_ANSWER_TTL_SECONDS = 4 * 60 * 60
PENDING_QUEUE_KEY = "runtime:answer_queue:pending"
PROCESSING_QUEUE_KEY = "runtime:answer_queue:processing"
SESSION_QUEUED_KEY_TEMPLATE = "runtime:answer_queue:queued:{session_id}"
PROCESS_LOCK_KEY = "runtime:answer_queue:flush:lock"
PROCESS_LOCK_TTL_SECONDS = 60
DEFAULT_FLUSH_BATCH_SIZE = 50
DEFAULT_DRAIN_INTERVAL_SECONDS = 2.0


def session_answers_key(session_id: int) -> str:
    return f"runtime:session:{session_id}:answers"


def session_dirty_questions_key(session_id: int) -> str:
    return f"runtime:session:{session_id}:dirty_questions"


def session_answered_count_key(session_id: int) -> str:
    return f"runtime:session:{session_id}:answered_count"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _json_loads(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    try:
        decoded = json.loads(str(raw))
    except Exception:
        return {}
    return dict(decoded) if isinstance(decoded, dict) else {}


def _answer_write_mode() -> str:
    mode = str(getattr(settings, "answer_write_mode", "direct") or "direct").strip().lower()
    return mode if mode in {"queue", "hybrid"} else "direct"


def _answer_queue_percentage() -> int:
    try:
        percentage = int(getattr(settings, "answer_queue_percentage", 0) or 0)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, percentage))


def is_runtime_answer_buffer_enabled() -> bool:
    """Return whether runtime answer buffering infrastructure is globally enabled.

    This is intentionally a capability/flush check, not a canary routing
    decision. Use is_runtime_answer_buffer_enabled_for_session() for routing
    new writes.
    """
    return bool(
        getattr(settings, "answer_queue_enabled", False)
        and _answer_write_mode() in {"queue", "hybrid"}
    )


def _answer_buffer_seed(
    *,
    session_id: int,
    user_id: int | None = None,
    exam_id: int | None = None,
) -> str:
    if exam_id is not None and user_id is not None:
        return f"{int(exam_id)}:{int(session_id)}:{int(user_id)}"
    return str(int(session_id))


def _stable_answer_buffer_bucket(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def is_runtime_answer_buffer_enabled_for_session(
    session_id: int,
    user_id: int | None = None,
    exam_id: int | None = None,
) -> bool:
    """Deterministically choose whether a session enters runtime buffering."""
    if not is_runtime_answer_buffer_enabled():
        return False

    percentage = _answer_queue_percentage()
    if percentage <= 0:
        return False
    if percentage >= 100:
        return True

    seed = _answer_buffer_seed(session_id=session_id, user_id=user_id, exam_id=exam_id)
    return _stable_answer_buffer_bucket(seed) < percentage


async def _acquire_session_write_lock(db: AsyncSession, session_id: int) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :session_id)"),
        {"namespace": SESSION_WRITE_LOCK_NAMESPACE, "session_id": session_id},
    )


async def _ensure_active_session_for_user(
    db: AsyncSession,
    *,
    session_id: int,
    user_id: int,
) -> ExamSession:
    result = await db.execute(
        select(ExamSession).where(
            ExamSession.id == session_id,
            ExamSession.user_id == user_id,
            ExamSession.status.in_(["in_progress", "active"]),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan atau tidak aktif")
    return session


async def _valid_question_ids(db: AsyncSession, exam_id: int, question_ids: Iterable[int]) -> Set[int]:
    ids = {int(item) for item in question_ids if int(item or 0) > 0}
    if not ids:
        return set()
    result = await db.execute(
        select(Question.id).where(
            Question.exam_id == exam_id,
            Question.id.in_(ids),
        )
    )
    return {int(row[0]) for row in result.all()}


async def _enqueue_session_for_flush(redis: Any, session_id: int) -> None:
    queued_key = SESSION_QUEUED_KEY_TEMPLATE.format(session_id=session_id)
    first_enqueue = await redis.set(queued_key, "1", nx=True, ex=RUNTIME_ANSWER_TTL_SECONDS)
    if first_enqueue:
        await redis.rpush(PENDING_QUEUE_KEY, str(session_id))
        await redis.expire(PENDING_QUEUE_KEY, RUNTIME_ANSWER_TTL_SECONDS)


async def _write_answer_buffer(
    *,
    session_id: int,
    user_id: int,
    exam_id: int,
    answers: Sequence[Dict[str, Any]],
) -> int:
    if not answers:
        return 0

    redis = await get_redis()
    answers_key = session_answers_key(session_id)
    dirty_key = session_dirty_questions_key(session_id)
    answered_count_key = session_answered_count_key(session_id)

    mapping: Dict[str, str] = {}
    dirty_ids: List[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for item in answers:
        question_id = int(item.get("question_id") or 0)
        if question_id <= 0:
            continue
        payload = {
            "session_id": session_id,
            "user_id": user_id,
            "exam_id": exam_id,
            "question_id": question_id,
            "selected_option_id": item.get("selected_option_id"),
            "selected_option_ids": item.get("selected_option_ids"),
            "answer_text": item.get("answer_text"),
            "statement_answers": item.get("statement_answers"),
            "answer_metadata": item.get("answer_metadata") or {},
            "is_correct": item.get("is_correct"),
            "points_earned": item.get("points_earned"),
            "updated_at": now_iso,
        }
        mapping[str(question_id)] = _json_dumps(payload)
        dirty_ids.append(str(question_id))

    if not mapping:
        return 0

    pipe = redis.pipeline()
    pipe.hset(answers_key, mapping=mapping)
    pipe.sadd(dirty_key, *dirty_ids)
    pipe.expire(answers_key, RUNTIME_ANSWER_TTL_SECONDS)
    pipe.expire(dirty_key, RUNTIME_ANSWER_TTL_SECONDS)
    await pipe.execute()

    try:
        total_buffered_answers = int(await redis.hlen(answers_key) or 0)
        await redis.set(
            answered_count_key,
            total_buffered_answers,
            ex=RUNTIME_ANSWER_TTL_SECONDS,
        )
    except Exception:
        logger.debug("Failed to refresh runtime buffer answered count", exc_info=True)
    await _enqueue_session_for_flush(redis, session_id)
    return len(mapping)


class AnswerRuntimeBufferService:
    """Feature-flagged Redis runtime answer buffer."""

    def __init__(self, db: AsyncSession, current_user: Any):
        self.db = db
        self.current_user = current_user

    async def accept_single_answer(
        self,
        *,
        session: ExamSession,
        answer_data: Any,
        answer_metadata: Dict[str, Any],
        is_correct: Any,
        points_earned: Any,
    ) -> int:
        """Buffer one validated submit-answer payload for hybrid runtime mode."""
        return await _write_answer_buffer(
            session_id=int(session.id),
            user_id=int(self.current_user.id),
            exam_id=int(session.exam_id),
            answers=[
                {
                    "question_id": int(answer_data.question_id),
                    "selected_option_id": answer_data.selected_option_id,
                    "selected_option_ids": answer_data.selected_option_ids,
                    "answer_text": answer_data.answer_text,
                    "statement_answers": answer_data.statement_answers,
                    "answer_metadata": dict(answer_metadata or {}),
                    "is_correct": is_correct,
                    "points_earned": points_earned,
                }
            ],
        )

    async def accept_batch(self, batch_data: Any) -> Dict[str, Any]:
        session = await _ensure_active_session_for_user(
            self.db,
            session_id=int(batch_data.session_id),
            user_id=int(self.current_user.id),
        )
        deduped: Dict[int, Any] = {}
        for answer in batch_data.answers or []:
            deduped[int(answer.question_id)] = answer
        valid_ids = await _valid_question_ids(self.db, int(session.exam_id), deduped.keys())
        answers = [
            {
                "question_id": int(answer.question_id),
                "selected_option_id": answer.selected_option_id,
                "selected_option_ids": answer.selected_option_ids,
                "answer_text": answer.answer_text,
                "statement_answers": answer.statement_answers,
                "answer_metadata": dict(answer.answer_metadata or {}),
            }
            for answer in deduped.values()
            if int(answer.question_id) in valid_ids
        ]
        buffered_count = await _write_answer_buffer(
            session_id=int(session.id),
            user_id=int(self.current_user.id),
            exam_id=int(session.exam_id),
            answers=answers,
        )
        await self._update_runtime_counts(int(session.id), [int(a["question_id"]) for a in answers])
        await update_session_answers(int(session.id), {str(a["question_id"]): True for a in answers})
        return {
            "status": "buffered" if buffered_count > 0 else "no_changes",
            "queued_count": buffered_count,
            "queue_id": f"redis-{int(session.id)}",
            "timestamp": datetime.now(timezone.utc),
        }

    async def accept_journal_events(self, sync_data: Any, accepted_events: Sequence[tuple[str, Any]]) -> int:
        session = await _ensure_active_session_for_user(
            self.db,
            session_id=int(sync_data.session_id),
            user_id=int(self.current_user.id),
        )
        valid_ids = await _valid_question_ids(
            self.db,
            int(session.exam_id),
            [int(event.question_id) for _, event in accepted_events],
        )
        latest_by_question: Dict[int, tuple[str, Any]] = {}
        for event_id, event in accepted_events:
            question_id = int(event.question_id)
            if question_id not in valid_ids:
                continue
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

        answers: List[Dict[str, Any]] = []
        for question_id, (event_id, event) in latest_by_question.items():
            metadata = dict(event.answer_metadata or {})
            metadata["client_event_id"] = event_id
            metadata["client_sequence"] = int(event.sequence)
            metadata["client_local_timestamp_ms"] = int(event.local_timestamp_ms)
            metadata["sync_source"] = "answer_journal_v1"
            answers.append(
                {
                    "question_id": question_id,
                    "selected_option_id": event.selected_option_id,
                    "selected_option_ids": event.selected_option_ids,
                    "answer_text": event.answer_text,
                    "statement_answers": event.statement_answers,
                    "answer_metadata": metadata,
                }
            )

        buffered_count = await _write_answer_buffer(
            session_id=int(session.id),
            user_id=int(self.current_user.id),
            exam_id=int(session.exam_id),
            answers=answers,
        )
        await self._update_runtime_counts(int(session.id), [int(a["question_id"]) for a in answers])
        await update_session_answers(int(session.id), {str(a["question_id"]): True for a in answers})
        return buffered_count

    async def _update_runtime_counts(self, session_id: int, question_ids: List[int]) -> None:
        try:
            answered_count_runtime = await add_answered_questions_and_count(session_id, question_ids)
            if answered_count_runtime is not None:
                await update_runtime_snapshot_answered_count(
                    session_id,
                    expected_user_id=int(self.current_user.id),
                    answered_count=answered_count_runtime,
                    mark_stale=False,
                    status="in_progress",
                )
        except Exception:
            logger.debug("Runtime answered_count buffer update skipped", exc_info=True)


async def _claim_pending_sessions(redis: Any, batch_size: int) -> List[int]:
    sessions: List[int] = []
    for _ in range(max(1, int(batch_size or 1))):
        raw = await redis.lmove(PENDING_QUEUE_KEY, PROCESSING_QUEUE_KEY, "LEFT", "RIGHT")
        if raw is None:
            break
        session_id = int(raw or 0)
        if session_id > 0:
            sessions.append(session_id)
    return sessions


async def _ack_processing_session(redis: Any, session_id: int) -> None:
    await redis.lrem(PROCESSING_QUEUE_KEY, 0, str(session_id))
    await redis.lrem(PENDING_QUEUE_KEY, 0, str(session_id))
    await redis.delete(SESSION_QUEUED_KEY_TEMPLATE.format(session_id=session_id))


async def _restore_processing_session(redis: Any, session_id: int) -> None:
    await redis.lrem(PROCESSING_QUEUE_KEY, 1, str(session_id))
    await redis.rpush(PENDING_QUEUE_KEY, str(session_id))


async def _flush_session_buffer(db: AsyncSession, redis: Any, session_id: int) -> int:
    answers_key = session_answers_key(session_id)
    dirty_key = session_dirty_questions_key(session_id)
    dirty_question_ids = [int(item) for item in await redis.smembers(dirty_key) if int(item or 0) > 0]
    if not dirty_question_ids:
        await _ack_processing_session(redis, session_id)
        return 0

    raw_answers = await redis.hmget(answers_key, [str(qid) for qid in dirty_question_ids])
    payloads = [_json_loads(raw) for raw in raw_answers]
    payloads = [item for item in payloads if int(item.get("question_id") or 0) > 0]
    if not payloads:
        await _ack_processing_session(redis, session_id)
        return 0

    session_result = await db.execute(
        select(ExamSession).where(
            ExamSession.id == session_id,
            ExamSession.status.in_(["in_progress", "active"]),
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        await _ack_processing_session(redis, session_id)
        return 0

    await _acquire_session_write_lock(db, session_id)
    existing_result = await db.execute(
        select(Answer).where(
            Answer.session_id == session_id,
            Answer.question_id.in_([int(item["question_id"]) for item in payloads]),
        )
    )
    existing_by_question = {int(answer.question_id): answer for answer in existing_result.scalars().all()}

    changed_rows = 0
    now_utc = datetime.now(timezone.utc)
    flushed_question_ids: List[int] = []
    for item in payloads:
        question_id = int(item["question_id"])
        existing_answer = existing_by_question.get(question_id)
        incoming_metadata = dict(item.get("answer_metadata") or {})
        final_metadata, _ = merge_statement_answer_metadata(
            existing_metadata=dict(existing_answer.answer_metadata or {}) if existing_answer else {},
            incoming_metadata=incoming_metadata,
            incoming_statement_answers=item.get("statement_answers"),
        )
        if existing_answer:
            has_changed = (
                existing_answer.selected_option_id != item.get("selected_option_id")
                or existing_answer.selected_option_ids != item.get("selected_option_ids")
                or existing_answer.answer_text != item.get("answer_text")
                or dict(existing_answer.answer_metadata or {}) != final_metadata
            )
            if not has_changed:
                flushed_question_ids.append(question_id)
                continue
            existing_answer.selected_option_id = item.get("selected_option_id")
            existing_answer.selected_option_ids = item.get("selected_option_ids")
            existing_answer.answer_text = item.get("answer_text")
            existing_answer.answer_metadata = final_metadata
            existing_answer.answered_at = now_utc
            existing_answer.is_correct = item.get("is_correct")
            existing_answer.points_earned = item.get("points_earned")
            changed_rows += 1
        else:
            db.add(
                Answer(
                    session_id=session_id,
                    question_id=question_id,
                    selected_option_id=item.get("selected_option_id"),
                    selected_option_ids=item.get("selected_option_ids"),
                    answer_text=item.get("answer_text"),
                    answer_metadata=final_metadata,
                    answered_at=now_utc,
                    is_correct=item.get("is_correct"),
                    points_earned=item.get("points_earned"),
                )
            )
            changed_rows += 1
        flushed_question_ids.append(question_id)

    await db.commit()
    invalidate_session_answer_count_cache(session_id)
    if flushed_question_ids:
        await redis.srem(dirty_key, *[str(qid) for qid in flushed_question_ids])
    remaining_dirty = await redis.scard(dirty_key)
    if int(remaining_dirty or 0) == 0:
        await _ack_processing_session(redis, session_id)
    else:
        await _restore_processing_session(redis, session_id)
    return changed_rows


async def flush_runtime_answer_buffer_for_session(db: AsyncSession, session_id: int) -> int:
    """Synchronously flush one session's runtime answer buffer before final submit.

    This is intentionally session-scoped so final submit can be prioritized over
    background drains and admin monitoring. The function is a no-op unless the
    runtime buffer feature flags are active.
    """
    if not is_runtime_answer_buffer_enabled():
        return 0
    redis = await get_redis()
    dirty_count = await redis.scard(session_dirty_questions_key(session_id))
    if int(dirty_count or 0) <= 0:
        await _ack_processing_session(redis, session_id)
        return 0
    return await _flush_session_buffer(db, redis, session_id)


async def flush_runtime_answer_buffer_once(batch_size: int = DEFAULT_FLUSH_BATCH_SIZE) -> int:
    if not is_runtime_answer_buffer_enabled():
        return 0
    redis = await get_redis()
    token = datetime.now(timezone.utc).isoformat()
    acquired = await redis.set(PROCESS_LOCK_KEY, token, ex=PROCESS_LOCK_TTL_SECONDS, nx=True)
    if not acquired:
        return 0
    total = 0
    try:
        session_ids = await _claim_pending_sessions(redis, batch_size)
        if not session_ids:
            return 0
        async with async_session_write() as db:
            for session_id in session_ids:
                try:
                    total += await _flush_session_buffer(db, redis, session_id)
                except Exception:
                    await db.rollback()
                    await _restore_processing_session(redis, session_id)
                    logger.exception("Failed flushing runtime answer buffer session=%s", session_id)
        return total
    finally:
        try:
            current = await redis.get(PROCESS_LOCK_KEY)
            if current == token:
                await redis.delete(PROCESS_LOCK_KEY)
        except Exception:
            logger.debug("Failed to release runtime answer buffer lock", exc_info=True)


async def answer_runtime_buffer_drain_loop(stop_event: asyncio.Event) -> None:
    logger.info("Answer runtime buffer drain loop started")
    while not stop_event.is_set():
        try:
            await flush_runtime_answer_buffer_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Answer runtime buffer drain tick failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=DEFAULT_DRAIN_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
    logger.info("Answer runtime buffer drain loop stopped")
