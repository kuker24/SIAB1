"""
Restart-safe distributed lock and cooldown helpers.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)

RESTART_SAFE_EXEC_LOCK_KEY = "system:restart_safe:exec_lock"
RESTART_SAFE_LAST_EXEC_KEY = "system:restart_safe:last_exec"
RESTART_SAFE_EXEC_LOCK_SECONDS = 900
RESTART_SAFE_FULL_COOLDOWN_SECONDS = 15 * 60


def parse_iso_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


async def acquire_restart_safe_exec_lock(actor: str) -> bool:
    """
    Acquire distributed lock for restart-safe execution.

    Prevents concurrent/duplicate restart requests from dashboard double-clicks
    or parallel API calls across multiple workers.
    """
    try:
        redis = await get_redis()
        token = json.dumps(
            {"actor": actor, "at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False,
        )
        acquired = await redis.set(
            RESTART_SAFE_EXEC_LOCK_KEY,
            token,
            nx=True,
            ex=RESTART_SAFE_EXEC_LOCK_SECONDS,
        )
        return bool(acquired)
    except Exception as exc:
        # Fail-open: do not block emergency operations if Redis is unavailable.
        logger.warning("Failed acquiring restart-safe lock: %s", exc)
        return True


async def release_restart_safe_exec_lock() -> None:
    try:
        redis = await get_redis()
        await redis.delete(RESTART_SAFE_EXEC_LOCK_KEY)
    except Exception as exc:
        logger.warning("Failed releasing restart-safe lock: %s", exc)


async def get_restart_safe_last_exec() -> Optional[Dict[str, Any]]:
    try:
        redis = await get_redis()
        raw = await redis.get(RESTART_SAFE_LAST_EXEC_KEY)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Failed reading restart-safe last exec state: %s", exc)
        return None


async def set_restart_safe_last_exec(*, mode: str, actor: str, reason: Optional[str]) -> None:
    try:
        redis = await get_redis()
        payload = {
            "mode": str(mode or "unknown"),
            "actor": actor,
            "reason": reason or "",
            "at": datetime.now(timezone.utc).isoformat(),
        }
        await redis.set(
            RESTART_SAFE_LAST_EXEC_KEY,
            json.dumps(payload, ensure_ascii=False),
            ex=max(RESTART_SAFE_FULL_COOLDOWN_SECONDS * 6, 21600),
        )
    except Exception as exc:
        logger.warning("Failed writing restart-safe last exec state: %s", exc)


def build_restart_safe_cooldown_state(
    now: datetime,
    last_exec: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "cooldown_seconds": RESTART_SAFE_FULL_COOLDOWN_SECONDS,
        "last_full_restart_at": None,
        "last_full_restart_by": None,
        "remaining_seconds": 0,
        "active": False,
    }
    if not isinstance(last_exec, dict):
        return state
    if str(last_exec.get("mode") or "").lower() != "full":
        return state

    last_at = parse_iso_timestamp(last_exec.get("at"))
    state["last_full_restart_at"] = last_exec.get("at")
    state["last_full_restart_by"] = last_exec.get("actor")
    if not last_at:
        return state

    elapsed_seconds = max(0, int((now - last_at).total_seconds()))
    remaining = max(0, RESTART_SAFE_FULL_COOLDOWN_SECONDS - elapsed_seconds)
    state["remaining_seconds"] = remaining
    state["active"] = remaining > 0
    return state


__all__ = [
    "RESTART_SAFE_EXEC_LOCK_SECONDS",
    "RESTART_SAFE_FULL_COOLDOWN_SECONDS",
    "acquire_restart_safe_exec_lock",
    "build_restart_safe_cooldown_state",
    "get_restart_safe_last_exec",
    "parse_iso_timestamp",
    "release_restart_safe_exec_lock",
    "set_restart_safe_last_exec",
]
