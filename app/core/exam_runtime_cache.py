"""
Hot-path runtime cache helpers for exam session operations.
"""
from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.question import Question
from app.models.session import Answer
from app.models.user import User

EXAM_QUESTION_COUNT_LOCAL_CACHE_TTL_SECONDS = 60
SESSION_ANSWER_COUNT_LOCAL_CACHE_TTL_SECONDS = 2
PROGRESS_EVENT_MIN_INTERVAL_SECONDS = 2.0
SESSION_ACTIVITY_HEARTBEAT_MIN_INTERVAL_SECONDS = 8.0

_exam_question_count_local_cache: Dict[int, Tuple[float, int]] = {}
_session_answer_count_local_cache: Dict[int, Tuple[float, int]] = {}
_session_progress_next_publish_at: Dict[int, float] = {}
_session_activity_next_publish_at: Dict[int, float] = {}
_user_display_name_local_cache: Dict[int, Tuple[float, str]] = {}


def answer_has_meaningful_content_clause():
    """SQL clause to count only answers that actually contain payload."""
    return or_(
        Answer.selected_option_id.isnot(None),
        func.cardinality(Answer.selected_option_ids) > 0,
        func.length(func.trim(func.coalesce(Answer.answer_text, ""))) > 0,
        text("coalesce(answers.answer_metadata->'statement_answers', '{}'::jsonb) <> '{}'::jsonb"),
    )


async def get_exam_question_count_cached(db: AsyncSession, exam_id: int) -> int:
    """
    Return total question count with a short in-process cache.
    """
    now = time.monotonic()
    cached = _exam_question_count_local_cache.get(exam_id)
    if cached and now < cached[0]:
        return int(cached[1])

    result = await db.execute(select(func.count(Question.id)).where(Question.exam_id == exam_id))
    total = int(result.scalar() or 0)
    _exam_question_count_local_cache[exam_id] = (
        now + EXAM_QUESTION_COUNT_LOCAL_CACHE_TTL_SECONDS,
        total,
    )
    return total


async def get_session_answer_count_cached(db: AsyncSession, session_id: int) -> int:
    """
    Return answered question count with very short in-process cache.
    """
    now = time.monotonic()
    cached = _session_answer_count_local_cache.get(session_id)
    if cached and now < cached[0]:
        return int(cached[1])

    answered_count_result = await db.execute(
        select(func.count(func.distinct(Answer.question_id))).where(
            Answer.session_id == session_id,
            answer_has_meaningful_content_clause(),
        )
    )
    answered_count = int(answered_count_result.scalar() or 0)
    _session_answer_count_local_cache[session_id] = (
        now + SESSION_ANSWER_COUNT_LOCAL_CACHE_TTL_SECONDS,
        answered_count,
    )
    return answered_count


def invalidate_session_answer_count_cache(session_id: int) -> None:
    _session_answer_count_local_cache.pop(session_id, None)


def should_publish_progress_update(session_id: int) -> bool:
    """Throttle progress broadcasts to protect hot-path latency."""
    now = time.monotonic()
    next_allowed = _session_progress_next_publish_at.get(session_id, 0.0)
    if now < next_allowed:
        return False

    _session_progress_next_publish_at[session_id] = now + PROGRESS_EVENT_MIN_INTERVAL_SECONDS

    # Keep dictionary bounded for long-running processes.
    if len(_session_progress_next_publish_at) > 50000:
        stale = [sid for sid, ts in _session_progress_next_publish_at.items() if ts <= now]
        for sid in stale[:10000]:
            _session_progress_next_publish_at.pop(sid, None)

    return True


def should_update_session_activity(session_id: int) -> bool:
    """Throttle heartbeat writes to Redis on session status polling."""
    now = time.monotonic()
    next_allowed = _session_activity_next_publish_at.get(session_id, 0.0)
    if now < next_allowed:
        return False

    _session_activity_next_publish_at[session_id] = (
        now + SESSION_ACTIVITY_HEARTBEAT_MIN_INTERVAL_SECONDS
    )

    if len(_session_activity_next_publish_at) > 50000:
        stale = [sid for sid, ts in _session_activity_next_publish_at.items() if ts <= now]
        for sid in stale[:10000]:
            _session_activity_next_publish_at.pop(sid, None)

    return True


async def get_user_display_name_cached(db: AsyncSession, user_id: Optional[int]) -> Optional[str]:
    if not user_id:
        return None

    now = time.monotonic()
    cached = _user_display_name_local_cache.get(int(user_id))
    if cached and now < cached[0]:
        return cached[1]

    user_result = await db.execute(
        select(User.full_name, User.username).where(User.id == int(user_id))
    )
    user_row = user_result.first()
    if not user_row:
        return None

    display_name = str(user_row[0] or user_row[1] or "").strip() or None
    if display_name:
        _user_display_name_local_cache[int(user_id)] = (now + 300.0, display_name)
    return display_name


__all__ = [
    "answer_has_meaningful_content_clause",
    "get_exam_question_count_cached",
    "get_session_answer_count_cached",
    "get_user_display_name_cached",
    "invalidate_session_answer_count_cache",
    "should_publish_progress_update",
    "should_update_session_activity",
]
