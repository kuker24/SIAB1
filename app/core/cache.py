"""Cache utilities for system settings."""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select

from app.core.redis_pubsub import get_redis
from app.database import async_session_read
from app.core.apk_profiles import parse_signature_profiles, get_allowed_tokens
from app.core.singleflight import KeyedSingleFlight
from app.core.start_db_admission import start_db_segment
from app.models.system_settings import SystemSettings

logger = logging.getLogger(__name__)
_security_cache_fills = KeyedSingleFlight[str]()


async def _cache_get_json(cache_key: str) -> Optional[Any]:
    """Read JSON value from Redis cache, returns None on miss/error."""
    try:
        redis = await get_redis()
        cached = await redis.get(cache_key)
        if cached is None:
            return None
        return json.loads(cached)
    except Exception as exc:
        logger.warning(f"Redis get failed for {cache_key}: {exc}")
        return None


async def _cache_set_json(cache_key: str, value: Any, ttl_seconds: int = 60) -> None:
    """Write JSON value to Redis cache, fail-open on Redis errors."""
    try:
        redis = await get_redis()
        await redis.set(cache_key, json.dumps(value), ex=ttl_seconds)
    except Exception as exc:
        logger.warning(f"Redis set failed for {cache_key}: {exc}")


async def is_developer_mode_enabled() -> bool:
    """
    Check if developer/tester mode is enabled (with caching).
    Returns True if browser testing is allowed.
    """
    cache_key = "system:developer_mode"
    cached = await _cache_get_json(cache_key)
    if cached is not None:
        return bool(cached)

    async def fill() -> bool:
        refreshed = await _cache_get_json(cache_key)
        if refreshed is not None:
            return bool(refreshed)
        try:
            async with start_db_segment("security"):
                async with async_session_read() as db:
                    result = await db.execute(select(SystemSettings))
                    setting = result.scalar_one_or_none()
                    enabled = bool(setting.allow_browser_testing) if setting else False
            await _cache_set_json(cache_key, enabled, ttl_seconds=60)
            return enabled
        except Exception as exc:
            logger.error(f"Failed to check developer mode: {exc}")
            return False  # Fail secure - default to enforcing SEB

    return await _security_cache_fills.run(cache_key, fill)


async def clear_developer_mode_cache() -> None:
    """Clear cached system settings after update."""
    try:
        redis = await get_redis()
        await redis.delete(
            "system:developer_mode",
            "system:freeze_mode",
            "system:allowed_signatures",
            "system:allowed_apk_tokens",
        )
        logger.info("System settings cache cleared")
    except Exception as exc:
        logger.warning(f"Failed to clear cache: {exc}")


async def is_freeze_mode_enabled() -> bool:
    """
    Check if emergency freeze mode is enabled (with caching).
    Returns True when non-developer actions must be blocked.
    """
    cache_key = "system:freeze_mode"
    cached = await _cache_get_json(cache_key)
    if cached is not None:
        return bool(cached)

    async def fill() -> bool:
        refreshed = await _cache_get_json(cache_key)
        if refreshed is not None:
            return bool(refreshed)
        try:
            async with start_db_segment("security"):
                async with async_session_read() as db:
                    result = await db.execute(select(SystemSettings))
                    setting = result.scalar_one_or_none()
                    enabled = bool(getattr(setting, "freeze_mode", False)) if setting else False
            await _cache_set_json(cache_key, enabled, ttl_seconds=15)
            return enabled
        except Exception as exc:
            logger.error(f"Failed to check freeze mode: {exc}")
            return False

    return await _security_cache_fills.run(cache_key, fill)


async def get_allowed_signatures() -> list[str]:
    """Get allowed app signatures from DB (cached)."""
    cache_key = "system:allowed_signatures"
    cached = await _cache_get_json(cache_key)
    if cached is not None:
        return cached if isinstance(cached, list) else []

    async def fill() -> list[str]:
        refreshed = await _cache_get_json(cache_key)
        if refreshed is not None:
            return refreshed if isinstance(refreshed, list) else []
        try:
            async with start_db_segment("security"):
                async with async_session_read() as db:
                    result = await db.execute(select(SystemSettings))
                    setting = result.scalar_one_or_none()
                    signatures: list[str] = []
                    if setting and setting.allowed_signatures:
                        signatures = parse_signature_profiles(setting.allowed_signatures).get(
                            "all_signatures", []
                        )
            await _cache_set_json(cache_key, signatures, ttl_seconds=60)
            return signatures
        except Exception as exc:
            logger.error(f"Failed to get signatures: {exc}")
            return []

    return list(await _security_cache_fills.run(cache_key, fill))


async def get_allowed_apk_tokens() -> list[str]:
    """Get allowed APK tokens (stable + new update) from DB (cached)."""
    cache_key = "system:allowed_apk_tokens"
    cached = await _cache_get_json(cache_key)
    if cached is not None:
        return cached if isinstance(cached, list) else []

    try:
        async with async_session_read() as db:
            result = await db.execute(select(SystemSettings))
            setting = result.scalar_one_or_none()
            allowed_tokens = []
            if setting and setting.minimum_apk_token:
                allowed_tokens = get_allowed_tokens(setting.minimum_apk_token)
        await _cache_set_json(cache_key, allowed_tokens, ttl_seconds=60)
        return allowed_tokens
    except Exception as exc:
        logger.error(f"Failed to get allowed APK tokens: {exc}")
        return []
