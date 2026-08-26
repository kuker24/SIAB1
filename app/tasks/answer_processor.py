"""
Answer queue processor for high-concurrency submit flow.

This worker consumes Redis queue items and upserts answers in PostgreSQL.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from celery import shared_task
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.redis_pubsub import get_redis
from app.database import async_session_maker, create_task_engine
from app.models.question import Question
from app.models.session import Answer, ExamSession

logger = logging.getLogger(__name__)

PENDING_QUEUE_KEY = "answer_queue:pending"
PROCESSING_QUEUE_KEY = "answer_queue:processing"
PROCESS_LOCK_KEY = "answer_queue:processing:lock"
PROCESS_LOCK_TTL_SECONDS = 60


def _parse_optional_iso_datetime(raw_value: Any) -> Optional[datetime]:
    if not raw_value:
        return None
    if isinstance(raw_value, datetime):
        dt = raw_value
    else:
        raw = str(raw_value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def enqueue_answer_payload(payload: Dict[str, Any]) -> int:
    """
    Push answer payload to Redis pending queue.

    Returns current queue length after push.
    """
    redis = await get_redis()
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    queue_length = await redis.rpush(PENDING_QUEUE_KEY, serialized)
    return int(queue_length or 0)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def process_answer_queue(self, batch_size: int = 100) -> None:
    """Celery task wrapper for queue processing."""
    if not settings.answer_queue_processing_enabled():
        return
    loop: Optional[asyncio.AbstractEventLoop] = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(
            _run_queue_with_task_engine(max(1, int(batch_size or 1)))
        )
    except Exception as exc:
        logger.error("Error in process_answer_queue: %s", exc)
        self.retry(exc=exc)
    finally:
        if loop is not None:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()
            except Exception as exc:
                logger.error("Error closing event loop: %s", exc)


async def _run_queue_with_task_engine(batch_size: int) -> int:
    engine = create_task_engine()
    try:
        factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        return await _async_process_answer_queue(batch_size, session_factory=factory)
    finally:
        await engine.dispose()


async def process_answer_queue_once(batch_size: int = 100) -> int:
    """Process one queue batch and return processed rows."""
    return await _async_process_answer_queue(max(1, int(batch_size or 1)))


async def drain_answer_queue(max_rounds: int = 4, batch_size: int = 300) -> int:
    """
    Drain queue in bounded rounds.

    Used by final submit to reduce lag window between queue and scoring.
    """
    rounds = max(1, int(max_rounds or 1))
    size = max(1, int(batch_size or 1))
    total_processed = 0
    for _ in range(rounds):
        processed = await _async_process_answer_queue(size)
        total_processed += processed
        if processed <= 0:
            break
    return total_processed


async def _async_process_answer_queue(
    batch_size: int,
    session_factory: Any = None,
) -> int:
    """Async implementation of answer queue processing."""
    if not settings.answer_queue_processing_enabled():
        return 0

    import redis.asyncio as aioredis

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    processed_count = 0
    lock_token: Optional[str] = None
    try:
        lock_token = await _acquire_process_lock(redis_client)
        if not lock_token:
            return 0

        await _rescue_stuck_processing_items(redis_client, batch_size)
        raw_batch, answers_to_process = await _claim_answer_batch(redis_client, batch_size)
        if not answers_to_process:
            return 0

        answers_to_process.sort(
            key=lambda item: (
                int(item.get("session_id") or 0),
                int(item.get("question_id") or 0),
            )
        )

        factory = session_factory or async_session_maker
        async with factory() as db:
            try:
                valid_answers, dropped_invalid = await _filter_answers_with_existing_sessions(
                    db,
                    answers_to_process,
                )
                if dropped_invalid > 0:
                    logger.warning(
                        "Dropped %s stale answer-queue items (missing exam session)",
                        dropped_invalid,
                    )

                for answer_data in valid_answers:
                    await _upsert_answer(db, answer_data)
                await db.commit()
                await _acknowledge_processed_items(redis_client, raw_batch)
                processed_count = len(valid_answers)
                logger.info("Processed %s answers from queue", processed_count)
            except Exception as exc:
                await db.rollback()
                logger.error("Error processing answer batch: %s", exc)
                await _restore_processing_batch(redis_client, len(raw_batch))
                raise
    finally:
        if lock_token:
            await _release_process_lock(redis_client, lock_token)
        await redis_client.aclose()
    return processed_count


async def _acquire_process_lock(redis_client) -> Optional[str]:
    token = uuid4().hex
    acquired = await redis_client.set(
        PROCESS_LOCK_KEY,
        token,
        ex=PROCESS_LOCK_TTL_SECONDS,
        nx=True,
    )
    if not acquired:
        return None
    return token


async def _release_process_lock(redis_client, token: str) -> None:
    release_script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
      return redis.call('del', KEYS[1])
    end
    return 0
    """
    try:
        await redis_client.eval(release_script, 1, PROCESS_LOCK_KEY, token)
    except Exception as exc:
        logger.debug("Failed to release answer queue process lock: %s", exc)


async def _rescue_stuck_processing_items(redis_client, limit: int) -> int:
    """
    Move previously claimed-but-unacked items back to pending queue.
    """
    rescued = 0
    for _ in range(max(0, limit)):
        restored = await redis_client.lmove(
            PROCESSING_QUEUE_KEY,
            PENDING_QUEUE_KEY,
            "RIGHT",
            "LEFT",
        )
        if restored is None:
            break
        rescued += 1
    return rescued


async def _claim_answer_batch(
    redis_client,
    batch_size: int,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    raw_batch: List[str] = []
    answers_to_process: List[Dict[str, Any]] = []

    for _ in range(batch_size):
        raw_data = await redis_client.lmove(
            PENDING_QUEUE_KEY,
            PROCESSING_QUEUE_KEY,
            "LEFT",
            "RIGHT",
        )
        if raw_data is None:
            break

        raw_batch.append(raw_data)
        try:
            answers_to_process.append(json.loads(raw_data))
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in answer queue: %s", exc)
            await redis_client.lrem(PROCESSING_QUEUE_KEY, 1, raw_data)
            raw_batch.pop()

    return raw_batch, answers_to_process


async def _acknowledge_processed_items(redis_client, raw_batch: List[str]) -> None:
    for raw_data in raw_batch:
        await redis_client.lrem(PROCESSING_QUEUE_KEY, 1, raw_data)


async def _restore_processing_batch(redis_client, count: int) -> None:
    for _ in range(max(0, count)):
        restored = await redis_client.lmove(
            PROCESSING_QUEUE_KEY,
            PENDING_QUEUE_KEY,
            "RIGHT",
            "LEFT",
        )
        if restored is None:
            break


async def _filter_answers_with_existing_sessions(
    db,
    answers_to_process: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    """Remove queue payloads that reference sessions that no longer exist."""
    session_ids = {
        int(item.get("session_id") or 0)
        for item in answers_to_process
        if int(item.get("session_id") or 0) > 0
    }
    if not session_ids:
        return [], len(answers_to_process)

    rows = await db.execute(select(ExamSession.id).where(ExamSession.id.in_(session_ids)))
    existing_session_ids = {int(value) for value in rows.scalars().all()}

    valid_answers: List[Dict[str, Any]] = []
    dropped_invalid = 0
    for item in answers_to_process:
        session_id = int(item.get("session_id") or 0)
        if session_id <= 0 or session_id not in existing_session_ids:
            dropped_invalid += 1
            continue
        valid_answers.append(item)
    return valid_answers, dropped_invalid


async def _resolve_scoring(db, answer_data: Dict[str, Any]) -> Tuple[Any, Any]:
    if "is_correct" in answer_data and "points_earned" in answer_data:
        return answer_data.get("is_correct"), answer_data.get("points_earned")

    question_id = answer_data.get("question_id")
    question_result = await db.execute(
        select(Question).where(Question.id == question_id)
    )
    question = question_result.scalar_one_or_none()
    if not question:
        logger.warning("Question %s not found while processing answer queue", question_id)
        return False, 0.0

    validation_data = {
        "selected_option_id": answer_data.get("selected_option_id"),
        "selected_option_ids": answer_data.get("selected_option_ids"),
        "answer_text": answer_data.get("answer_text"),
        "matching_pairs": answer_data.get("matching_pairs"),
        "statement_answers": answer_data.get("statement_answers"),
    }
    return question.validate_answer(validation_data)


async def _upsert_answer(db, answer_data: Dict[str, Any]) -> None:
    """Insert/update a single answer using UPSERT."""
    session_id = answer_data.get("session_id")
    question_id = answer_data.get("question_id")
    if not session_id or not question_id:
        logger.warning("Invalid answer payload: missing session_id/question_id")
        return

    is_correct, points_earned = await _resolve_scoring(db, answer_data)
    answer_metadata = dict(answer_data.get("answer_metadata") or {})
    if answer_data.get("statement_answers"):
        answer_metadata["statement_answers"] = answer_data.get("statement_answers")

    answered_at = _parse_optional_iso_datetime(answer_data.get("answered_at")) or datetime.now(
        timezone.utc
    )
    write_fields = {
        "selected_option_id": answer_data.get("selected_option_id"),
        "selected_option_ids": answer_data.get("selected_option_ids"),
        "answer_text": answer_data.get("answer_text"),
        "matching_pairs": answer_data.get("matching_pairs"),
        "answer_metadata": answer_metadata,
        "is_correct": is_correct,
        "points_earned": points_earned,
        "answered_at": answered_at,
    }

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
        )
    )
    try:
        await db.execute(upsert_stmt)
    except Exception as exc:
        raw_error = str(exc).lower()
        if "answers_session_id_fkey" in raw_error or (
            "foreign key constraint" in raw_error and "session_id" in raw_error
        ):
            logger.warning(
                "Skip stale queue answer for missing session_id=%s question_id=%s",
                session_id,
                question_id,
            )
            return
        if "no unique or exclusion constraint" not in raw_error:
            raise
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:session_id, :question_id)"),
            {"session_id": int(session_id), "question_id": int(question_id)},
        )
        update_stmt = (
            Answer.__table__.update()
            .where(
                Answer.session_id == int(session_id),
                Answer.question_id == int(question_id),
            )
            .values(**write_fields)
        )
        update_result = await db.execute(update_stmt)
        if (update_result.rowcount or 0) == 0:
            db.add(
                Answer(
                    session_id=int(session_id),
                    question_id=int(question_id),
                    **write_fields,
                )
            )
