"""
Redis-backed runtime state helpers for active exam sessions.

This module keeps lightweight, frequently-updated runtime counters in Redis so
hot monitoring/polling paths can avoid repetitive DB aggregate queries.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from app.core.redis_pubsub import get_redis, get_session_data, store_session_data

RUNTIME_ANSWERED_SET_TTL_SECONDS = 7200


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _answered_set_key(session_id: int) -> str:
    return f"exam_answered_questions:{int(session_id)}"


def _normalize_question_ids(question_ids: Iterable[Any]) -> List[str]:
    normalized: List[str] = []
    seen: set[int] = set()
    for raw in question_ids:
        value = _safe_int(raw)
        if value is None or value <= 0 or value in seen:
            continue
        seen.add(value)
        normalized.append(str(value))
    return normalized


async def get_runtime_snapshots_bulk(session_ids: Iterable[Any]) -> Dict[int, Dict[str, Any]]:
    """
    Fetch exam_session:{session_id} snapshots in one MGET call.
    """
    normalized_ids: List[int] = []
    seen: set[int] = set()
    for raw_id in session_ids:
        sid = _safe_int(raw_id)
        if sid is None or sid <= 0 or sid in seen:
            continue
        seen.add(sid)
        normalized_ids.append(sid)

    if not normalized_ids:
        return {}

    redis = await get_redis()
    keys = [f"exam_session:{sid}" for sid in normalized_ids]
    raw_values = await redis.mget(keys)
    snapshots: Dict[int, Dict[str, Any]] = {}
    for sid, raw in zip(normalized_ids, raw_values):
        if raw is None:
            continue
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            payload = json.loads(raw)
            if isinstance(payload, dict):
                snapshots[sid] = payload
        except Exception:
            continue
    return snapshots


async def add_answered_questions_and_count(
    session_id: int,
    question_ids: Iterable[Any],
) -> Optional[int]:
    """
    Add answered question IDs into Redis set and return resulting unique count.
    """
    normalized_ids = _normalize_question_ids(question_ids)
    if not normalized_ids:
        return None

    redis = await get_redis()
    key = _answered_set_key(session_id)
    pipe = redis.pipeline()
    pipe.sadd(key, *normalized_ids)
    pipe.expire(key, RUNTIME_ANSWERED_SET_TTL_SECONDS)
    pipe.scard(key)
    results = await pipe.execute()
    count = _safe_int(results[-1] if results else None)
    return max(0, count or 0)


async def get_answered_count_from_set(session_id: int) -> Optional[int]:
    """
    Return answered count from Redis set when available.
    Returns None when set does not exist yet.
    """
    redis = await get_redis()
    key = _answered_set_key(session_id)
    exists = await redis.exists(key)
    if not bool(exists):
        return None
    count = _safe_int(await redis.scard(key))
    return max(0, count or 0)


async def get_answered_counts_bulk(session_ids: Iterable[Any]) -> Dict[int, int]:
    """
    Bulk-read answered counts from Redis sets.
    Only returns sessions whose set already exists.
    """
    normalized_ids: List[int] = []
    seen: set[int] = set()
    for raw_id in session_ids:
        sid = _safe_int(raw_id)
        if sid is None or sid <= 0 or sid in seen:
            continue
        seen.add(sid)
        normalized_ids.append(sid)

    if not normalized_ids:
        return {}

    redis = await get_redis()
    keys = [_answered_set_key(sid) for sid in normalized_ids]
    pipe = redis.pipeline()
    for key in keys:
        pipe.exists(key)
    for key in keys:
        pipe.scard(key)
    results = await pipe.execute()
    midpoint = len(keys)
    exists_flags = results[:midpoint]
    counts = results[midpoint:]

    payload: Dict[int, int] = {}
    for sid, exists_flag, raw_count in zip(normalized_ids, exists_flags, counts):
        if not bool(exists_flag):
            continue
        count = _safe_int(raw_count)
        payload[sid] = max(0, count or 0)
    return payload


async def update_runtime_snapshot_answered_count(
    session_id: int,
    *,
    expected_user_id: Optional[int],
    answered_count: int,
    mark_stale: bool = False,
    status: Optional[str] = None,
) -> None:
    """
    Patch Redis runtime snapshot with answered_count and staleness flags.
    """
    snapshot = await get_session_data(session_id)
    if snapshot is None:
        return
    if not isinstance(snapshot, dict):
        return
    if expected_user_id is not None:
        snapshot_user_id = _safe_int(snapshot.get("user_id"))
        if snapshot_user_id is not None and snapshot_user_id != int(expected_user_id):
            return

    snapshot["answered_count"] = max(0, int(answered_count))
    snapshot["answered_count_stale"] = bool(mark_stale)
    if status:
        snapshot["status"] = str(status)
    await store_session_data(session_id, snapshot)


__all__ = [
    "add_answered_questions_and_count",
    "get_answered_count_from_set",
    "get_answered_counts_bulk",
    "get_runtime_snapshots_bulk",
    "update_runtime_snapshot_answered_count",
]
