"""
User list/class cache helpers (local + Redis).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi.encoders import jsonable_encoder

from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)

STUDENT_CLASSES_CACHE_TTL_SECONDS = 60
_student_classes_cache: Dict[str, Any] = {
    "expires_at": 0.0,
    "classes": None,
}

USERS_LIST_CACHE_TTL_SECONDS = 15
_users_list_cache: Dict[Any, Dict[str, Any]] = {}
USERS_REDIS_LIST_CACHE_TTL_SECONDS = 30
USERS_REDIS_CLASSES_CACHE_TTL_SECONDS = 180
USERS_REDIS_LIST_CACHE_PREFIX = "cache:users:list:v1"
USERS_REDIS_CLASSES_CACHE_KEY = "cache:users:student-classes:v1"


def _build_users_list_redis_key(cache_key: Any) -> str:
    raw_key = json.dumps(cache_key, separators=(",", ":"), ensure_ascii=True, default=str)
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return f"{USERS_REDIS_LIST_CACHE_PREFIX}:{digest}"


async def _redis_cache_get_json(cache_key: str) -> Optional[Any]:
    try:
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached is None:
            return None
        return json.loads(cached)
    except Exception as exc:
        logger.warning("Redis get failed for %s: %s", cache_key, str(exc))
        return None


async def _redis_cache_set_json(cache_key: str, value: Any, ttl_seconds: int) -> None:
    try:
        redis = await get_redis()
        encoded = json.dumps(jsonable_encoder(value), separators=(",", ":"), ensure_ascii=False)
        await redis.set(cache_key, encoded, ex=ttl_seconds)
    except Exception as exc:
        logger.warning("Redis set failed for %s: %s", cache_key, str(exc))


async def _get_cached_users_list_redis(cache_key: Any) -> Optional[List[Dict[str, Any]]]:
    redis_key = _build_users_list_redis_key(cache_key)
    cached = await _redis_cache_get_json(redis_key)
    if isinstance(cached, list):
        return cached
    return None


async def _set_cached_users_list_redis(cache_key: Any, data: List[Dict[str, Any]]) -> None:
    redis_key = _build_users_list_redis_key(cache_key)
    await _redis_cache_set_json(redis_key, data, USERS_REDIS_LIST_CACHE_TTL_SECONDS)


async def _get_cached_student_classes_redis() -> Optional[List[str]]:
    cached = await _redis_cache_get_json(USERS_REDIS_CLASSES_CACHE_KEY)
    if isinstance(cached, list):
        return [str(item) for item in cached if isinstance(item, str) and item.strip()]
    return None


async def _set_cached_student_classes_redis(classes: List[str]) -> None:
    await _redis_cache_set_json(
        USERS_REDIS_CLASSES_CACHE_KEY,
        classes,
        USERS_REDIS_CLASSES_CACHE_TTL_SECONDS,
    )


def _get_cached_student_classes() -> Optional[List[str]]:
    cached_classes = _student_classes_cache.get("classes")
    expires_at = _student_classes_cache.get("expires_at", 0.0)
    if cached_classes is None:
        return None
    if time.monotonic() >= expires_at:
        _student_classes_cache["classes"] = None
        _student_classes_cache["expires_at"] = 0.0
        return None
    return cached_classes


def _set_cached_student_classes(classes: List[str]) -> None:
    _student_classes_cache["classes"] = classes
    _student_classes_cache["expires_at"] = (
        time.monotonic() + STUDENT_CLASSES_CACHE_TTL_SECONDS
    )


def _get_cached_users_list(cache_key: Any) -> Optional[List[Dict[str, Any]]]:
    entry = _users_list_cache.get(cache_key)
    if not entry:
        return None
    if time.monotonic() >= entry["expires_at"]:
        _users_list_cache.pop(cache_key, None)
        return None
    return entry["data"]


def _set_cached_users_list(cache_key: Any, data: List[Dict[str, Any]]) -> None:
    # Keep cache bounded to avoid unbounded growth in long-lived workers.
    if len(_users_list_cache) > 128:
        now = time.monotonic()
        expired_keys = [
            key for key, value in _users_list_cache.items()
            if value.get("expires_at", 0.0) <= now
        ]
        for key in expired_keys:
            _users_list_cache.pop(key, None)
        if len(_users_list_cache) > 128:
            _users_list_cache.clear()

    _users_list_cache[cache_key] = {
        "expires_at": time.monotonic() + USERS_LIST_CACHE_TTL_SECONDS,
        "data": data,
    }


def _invalidate_user_caches() -> None:
    _users_list_cache.clear()
    _student_classes_cache["classes"] = None
    _student_classes_cache["expires_at"] = 0.0


async def _invalidate_user_caches_redis() -> None:
    try:
        redis = await get_redis()
        await redis.delete(USERS_REDIS_CLASSES_CACHE_KEY)

        batch: List[str] = []
        async for key in redis.scan_iter(match=f"{USERS_REDIS_LIST_CACHE_PREFIX}:*", count=256):
            batch.append(str(key))
            if len(batch) >= 256:
                await redis.delete(*batch)
                batch.clear()

        if batch:
            await redis.delete(*batch)
    except Exception as exc:
        logger.warning("Failed invalidating users redis caches: %s", str(exc))


__all__ = [
    "_get_cached_student_classes",
    "_get_cached_student_classes_redis",
    "_get_cached_users_list",
    "_get_cached_users_list_redis",
    "_invalidate_user_caches",
    "_invalidate_user_caches_redis",
    "_set_cached_student_classes",
    "_set_cached_student_classes_redis",
    "_set_cached_users_list",
    "_set_cached_users_list_redis",
]
