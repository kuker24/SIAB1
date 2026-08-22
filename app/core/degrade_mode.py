"""
Runtime degrade mode policy.

Degrade mode is a short-lived protection profile for peak traffic windows.
State is stored in Redis to remain consistent across API replicas.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)


DEGRADE_MODE_KEY = "system:degrade_mode"
RESOURCE_MODE_KEY = "system:resource_mode"
DEGRADE_CACHE_TTL_SECONDS = 3
RESOURCE_MODE_CACHE_TTL_SECONDS = 3


NORMAL_POLICY: Dict[str, Any] = {
    "degrade_mode": False,
    "auto_save_interval_ms": 35_000,
    "answer_sync_debounce_ms": 6_000,
    "admin_refresh_interval_ms": 12_000,
    "monitor_modal_poll_interval_ms": 15_000,
    "student_detail_poll_interval_ms": 10_000,
    "fullscreen_monitor_poll_interval_ms": 10_000,
    "non_critical_min_interval_ms": 0,
}

HIGH_POLICY_OVERRIDES: Dict[str, Any] = {
    "degrade_mode": True,
    "auto_save_interval_ms": 38_000,
    "answer_sync_debounce_ms": 6_000,
    "admin_refresh_interval_ms": 12_000,
    "monitor_modal_poll_interval_ms": 18_000,
    "student_detail_poll_interval_ms": 12_000,
    "fullscreen_monitor_poll_interval_ms": 12_000,
    "non_critical_min_interval_ms": 8_000,
}

EXTREME_POLICY_OVERRIDES: Dict[str, Any] = {
    "degrade_mode": True,
    "auto_save_interval_ms": 45_000,
    "answer_sync_debounce_ms": 8_000,
    "admin_refresh_interval_ms": 15_000,
    "monitor_modal_poll_interval_ms": 20_000,
    "student_detail_poll_interval_ms": 15_000,
    "fullscreen_monitor_poll_interval_ms": 15_000,
    "non_critical_min_interval_ms": 12_000,
}

RESOURCE_MODE_CATALOG: Dict[str, Dict[str, Any]] = {
    "normal": {
        "label": "Normal",
        "description": "Distribusi seimbang ke semua komponen.",
        "delayed_features": [],
    },
    "high": {
        "label": "High",
        "description": "Ujian diprioritaskan dengan throttling ringan; monitoring admin/guru tetap responsif.",
        "delayed_features": [
            "Analytics historis non-ujian refresh lebih lambat",
            "Sinkronisasi non-prioritas ditunda ringan",
        ],
    },
    "extreme": {
        "label": "Extreme",
        "description": "Fokus utama ke stabilitas ujian saat darurat; monitoring admin/guru tetap dipertahankan.",
        "delayed_features": [
            "Analytics historis dibatasi sementara",
            "Pekerjaan background non-ujian ditunda maksimal",
        ],
    },
}


_cached_state: Optional[Dict[str, Any]] = None
_cached_at: float = 0.0
_cached_resource_state: Optional[Dict[str, Any]] = None
_cached_resource_at: float = 0.0


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_cache_fresh() -> bool:
    if _cached_state is None:
        return False
    return (time.monotonic() - _cached_at) < DEGRADE_CACHE_TTL_SECONDS


def _set_cache(value: Dict[str, Any]) -> None:
    global _cached_state, _cached_at
    _cached_state = value
    _cached_at = time.monotonic()


def _clear_cache() -> None:
    global _cached_state, _cached_at
    _cached_state = None
    _cached_at = 0.0


def _is_resource_cache_fresh() -> bool:
    if _cached_resource_state is None:
        return False
    return (time.monotonic() - _cached_resource_at) < RESOURCE_MODE_CACHE_TTL_SECONDS


def _set_resource_cache(value: Dict[str, Any]) -> None:
    global _cached_resource_state, _cached_resource_at
    _cached_resource_state = value
    _cached_resource_at = time.monotonic()


def _clear_resource_cache() -> None:
    global _cached_resource_state, _cached_resource_at
    _cached_resource_state = None
    _cached_resource_at = 0.0


def _build_disabled_state() -> Dict[str, Any]:
    return {
        "enabled": False,
        "reason": None,
        "source": None,
        "actor": None,
        "activated_at": None,
        "expires_at": None,
    }


def _build_default_resource_mode_state() -> Dict[str, Any]:
    return {
        "mode": "normal",
        "reason": "Default normal mode",
        "source": "default",
        "actor": None,
        "updated_at": None,
        "expires_at": None,
    }


async def get_degrade_mode_state(force_refresh: bool = False) -> Dict[str, Any]:
    """Return degrade mode state payload."""
    if not force_refresh and _is_cache_fresh():
        return dict(_cached_state or _build_disabled_state())

    try:
        redis = await get_redis()
        raw = await redis.get(DEGRADE_MODE_KEY)
        if not raw:
            state = _build_disabled_state()
            _set_cache(state)
            return dict(state)

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")

        payload = json.loads(raw)
        enabled = bool(payload.get("enabled", False))
        expires_at_raw = payload.get("expires_at")
        if enabled and expires_at_raw:
            try:
                expires_at = datetime.fromisoformat(expires_at_raw)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at < datetime.now(timezone.utc):
                    await redis.delete(DEGRADE_MODE_KEY)
                    state = _build_disabled_state()
                    _set_cache(state)
                    return dict(state)
            except Exception:
                logger.warning("Invalid degrade mode expiry payload, resetting state")
                await redis.delete(DEGRADE_MODE_KEY)
                state = _build_disabled_state()
                _set_cache(state)
                return dict(state)

        normalized = {
            "enabled": enabled,
            "reason": payload.get("reason"),
            "source": payload.get("source"),
            "actor": payload.get("actor"),
            "activated_at": payload.get("activated_at"),
            "expires_at": payload.get("expires_at"),
        }
        _set_cache(normalized)
        return dict(normalized)
    except Exception as exc:
        logger.warning("Failed to fetch degrade mode state: %s", exc)
        state = _build_disabled_state()
        _set_cache(state)
        return dict(state)


def get_resource_mode_catalog() -> Dict[str, Dict[str, Any]]:
    """Public catalog for admin UI explanations."""
    return {key: dict(value) for key, value in RESOURCE_MODE_CATALOG.items()}


async def get_resource_mode_state(force_refresh: bool = False) -> Dict[str, Any]:
    """Return adaptive resource mode state."""
    if not force_refresh and _is_resource_cache_fresh():
        return dict(_cached_resource_state or _build_default_resource_mode_state())

    default_state = _build_default_resource_mode_state()
    try:
        redis = await get_redis()
        raw = await redis.get(RESOURCE_MODE_KEY)
        if not raw:
            _set_resource_cache(default_state)
            return dict(default_state)

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")

        payload = json.loads(raw)
        mode = str(payload.get("mode") or "normal").lower()
        if mode not in RESOURCE_MODE_CATALOG:
            mode = "normal"

        expires_at_raw = payload.get("expires_at")
        if expires_at_raw:
            try:
                expires_at = datetime.fromisoformat(expires_at_raw)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at < datetime.now(timezone.utc):
                    await redis.delete(RESOURCE_MODE_KEY)
                    _set_resource_cache(default_state)
                    return dict(default_state)
            except Exception:
                await redis.delete(RESOURCE_MODE_KEY)
                _set_resource_cache(default_state)
                return dict(default_state)

        normalized = {
            "mode": mode,
            "reason": payload.get("reason"),
            "source": payload.get("source"),
            "actor": payload.get("actor"),
            "updated_at": payload.get("updated_at"),
            "expires_at": payload.get("expires_at"),
        }
        _set_resource_cache(normalized)
        return dict(normalized)
    except Exception as exc:
        logger.warning("Failed to fetch resource mode state: %s", exc)
        _set_resource_cache(default_state)
        return dict(default_state)


async def set_resource_mode(
    *,
    mode: str,
    reason: Optional[str] = None,
    source: str = "manual",
    actor: Optional[str] = None,
    ttl_minutes: int = 120,
) -> Dict[str, Any]:
    """Set adaptive resource mode shared across API replicas."""
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in RESOURCE_MODE_CATALOG:
        normalized_mode = "normal"

    expires_at = None
    ttl_seconds = None
    if normalized_mode != "normal":
        ttl_minutes = max(5, min(ttl_minutes, 24 * 60))
        expires_at_dt = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        expires_at = expires_at_dt.isoformat()
        ttl_seconds = ttl_minutes * 60

    state = {
        "mode": normalized_mode,
        "reason": reason or f"Resource mode {normalized_mode} selected",
        "source": source,
        "actor": actor,
        "updated_at": _now_utc_iso(),
        "expires_at": expires_at,
    }

    try:
        redis = await get_redis()
        if normalized_mode == "normal":
            await redis.delete(RESOURCE_MODE_KEY)
        else:
            await redis.set(RESOURCE_MODE_KEY, json.dumps(state), ex=ttl_seconds)
    except Exception as exc:
        logger.warning("Failed to persist resource mode state: %s", exc)

    _set_resource_cache(state if normalized_mode != "normal" else _build_default_resource_mode_state())
    logger.warning(
        "Resource mode updated mode=%s source=%s actor=%s reason=%s",
        normalized_mode,
        source,
        actor,
        state["reason"],
    )
    return dict(state)


async def set_degrade_mode(
    *,
    enabled: bool,
    reason: Optional[str] = None,
    source: str = "manual",
    actor: Optional[str] = None,
    ttl_minutes: int = 120,
) -> Dict[str, Any]:
    """Enable or disable degrade mode with shared Redis state."""
    if not enabled:
        return await disable_degrade_mode(actor=actor, source=source)

    ttl_minutes = max(5, min(ttl_minutes, 24 * 60))
    activated_at = datetime.now(timezone.utc)
    expires_at = activated_at + timedelta(minutes=ttl_minutes)

    state = {
        "enabled": True,
        "reason": reason or "Peak protection enabled",
        "source": source,
        "actor": actor,
        "activated_at": activated_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    try:
        redis = await get_redis()
        await redis.set(DEGRADE_MODE_KEY, json.dumps(state), ex=ttl_minutes * 60)
        _set_cache(state)
        logger.warning(
            "Degrade mode enabled source=%s actor=%s ttl_minutes=%s reason=%s",
            source,
            actor,
            ttl_minutes,
            state["reason"],
        )
    except Exception as exc:
        logger.error("Failed to set degrade mode in Redis: %s", exc)
        _set_cache(state)
    return dict(state)


async def disable_degrade_mode(
    *,
    actor: Optional[str] = None,
    source: str = "manual",
) -> Dict[str, Any]:
    """Disable degrade mode immediately."""
    state = _build_disabled_state()
    try:
        redis = await get_redis()
        await redis.delete(DEGRADE_MODE_KEY)
    except Exception as exc:
        logger.warning("Failed to clear degrade mode key: %s", exc)

    _set_cache(state)
    logger.warning("Degrade mode disabled source=%s actor=%s at=%s", source, actor, _now_utc_iso())
    return dict(state)


async def get_runtime_policy(force_refresh: bool = False) -> Dict[str, Any]:
    """Return runtime policy used by frontend and request guards."""
    state = await get_degrade_mode_state(force_refresh=force_refresh)
    resource_state = await get_resource_mode_state(force_refresh=force_refresh)

    mode_from_resource = str(resource_state.get("mode") or "normal").lower()
    if mode_from_resource not in RESOURCE_MODE_CATALOG:
        mode_from_resource = "normal"
    if mode_from_resource == "normal" and state.get("enabled"):
        effective_mode = "high"
    else:
        effective_mode = mode_from_resource

    policy = dict(NORMAL_POLICY)
    if effective_mode == "high":
        policy.update(HIGH_POLICY_OVERRIDES)
    elif effective_mode == "extreme":
        policy.update(EXTREME_POLICY_OVERRIDES)

    mode_meta = RESOURCE_MODE_CATALOG.get(effective_mode, RESOURCE_MODE_CATALOG["normal"])
    policy.update(
        {
            "resource_mode": effective_mode,
            "resource_mode_label": mode_meta.get("label"),
            "resource_mode_description": mode_meta.get("description"),
            "delayed_features": mode_meta.get("delayed_features", []),
            "resource_mode_reason": resource_state.get("reason"),
            "resource_mode_source": resource_state.get("source"),
            "resource_mode_actor": resource_state.get("actor"),
            "resource_mode_updated_at": resource_state.get("updated_at"),
            "resource_mode_expires_at": resource_state.get("expires_at"),
            "reason": state.get("reason"),
            "source": state.get("source"),
            "actor": state.get("actor"),
            "activated_at": state.get("activated_at"),
            "expires_at": state.get("expires_at"),
            "server_time": _now_utc_iso(),
        }
    )
    return policy
