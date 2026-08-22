"""
Redis-backed cache helpers for exam results payloads.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Protocol

from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)

EXAM_RESULTS_CACHE_PREFIX = "cache:exam-results:v1"
EXAM_RESULTS_CACHE_TTL_SECONDS = 30
EXAM_RESULTS_BREAKDOWN_CACHE_TTL_SECONDS = 15


class ExamResultsViewerLike(Protocol):
    id: int
    is_admin: bool


def build_exam_results_cache_key(exam_id: int, include_breakdown: bool, viewer_scope: str) -> str:
    breakdown_flag = "1" if include_breakdown else "0"
    return f"{EXAM_RESULTS_CACHE_PREFIX}:{exam_id}:b{breakdown_flag}:{viewer_scope}"


def build_exam_results_viewer_scope(current_user: ExamResultsViewerLike, creator_id: int) -> str:
    if bool(getattr(current_user, "is_admin", False)):
        return "admin"
    return f"creator:{creator_id}:viewer:{current_user.id}"


async def get_cached_exam_results(cache_key: str) -> Optional[List[Dict[str, Any]]]:
    try:
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached is None:
            return None
        parsed = json.loads(cached)
        if isinstance(parsed, list):
            return parsed
        return None
    except Exception as exc:
        logger.warning("Failed reading exam results cache key %s: %s", cache_key, str(exc))
        return None


async def set_cached_exam_results(
    cache_key: str,
    payload: List[Dict[str, Any]],
    *,
    include_breakdown: bool,
) -> None:
    try:
        redis = await get_redis()
        ttl = (
            EXAM_RESULTS_BREAKDOWN_CACHE_TTL_SECONDS
            if include_breakdown
            else EXAM_RESULTS_CACHE_TTL_SECONDS
        )
        await redis.set(cache_key, json.dumps(payload, default=str, ensure_ascii=False), ex=ttl)
    except Exception as exc:
        logger.warning("Failed writing exam results cache key %s: %s", cache_key, str(exc))


async def invalidate_exam_results_cache(exam_id: int) -> None:
    try:
        redis = await get_redis()
        batch: List[str] = []
        async for key in redis.scan_iter(match=f"{EXAM_RESULTS_CACHE_PREFIX}:{exam_id}:*", count=256):
            batch.append(str(key))
            if len(batch) >= 256:
                await redis.delete(*batch)
                batch.clear()
        if batch:
            await redis.delete(*batch)
    except Exception as exc:
        logger.warning("Failed invalidating exam results cache for exam %s: %s", exam_id, str(exc))


__all__ = [
    "build_exam_results_cache_key",
    "build_exam_results_viewer_scope",
    "get_cached_exam_results",
    "invalidate_exam_results_cache",
    "set_cached_exam_results",
]
