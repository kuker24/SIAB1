"""
Peak protection middleware for non-critical endpoints during degrade mode.
"""

from __future__ import annotations

import logging
import re
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.client_ip import get_client_ip
from app.core.degrade_mode import get_runtime_policy
from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)


NON_CRITICAL_PREFIXES = (
    "/api/analytics",
    "/api/activity",
)

NON_CRITICAL_EXACT = set()

NON_CRITICAL_REGEX = ()

ADMIN_PROTECTED_PREFIXES = (
    "/api/monitoring",
    "/api/users",
    "/api/v1/settings",
    "/api/stats",
    "/api/alerts",
)

ESSENTIAL_PREFIXES = (
    "/health",
    "/static/",
    "/api/auth/",
    "/api/exams/submit",
    "/api/exams/submit-answer",
    "/api/exams/auto-save",
    "/api/exams/auto-save-batch",
    "/api/exams/session/",
    "/api/exams/join",
    "/ws/",
)

ESSENTIAL_EXACT = {
    "/api/monitoring/runtime-policy",
}


def _is_essential_path(path: str) -> bool:
    if path in ESSENTIAL_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in ADMIN_PROTECTED_PREFIXES):
        return True
    return any(path.startswith(prefix) for prefix in ESSENTIAL_PREFIXES)


def _is_non_critical_path(path: str) -> bool:
    if path in NON_CRITICAL_EXACT:
        return True
    if any(path.startswith(prefix) for prefix in NON_CRITICAL_PREFIXES):
        return True
    return any(pattern.match(path) for pattern in NON_CRITICAL_REGEX)


def _build_throttle_key(client_ip: str, path: str) -> str:
    """
    Build a stable degrade-throttle key.

    Query strings are intentionally excluded so callers cannot bypass the guard
    by appending random nonce parameters during high-traffic protection.
    """
    return f"degrade:throttle:{client_ip}:{path}"


class DegradeModeGuardMiddleware(BaseHTTPMiddleware):
    """Throttle expensive/non-critical endpoints during traffic degradation."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        policy = await get_runtime_policy()
        request.state.runtime_policy = policy

        is_degrade = bool(policy.get("degrade_mode", False))
        min_interval_ms = int(policy.get("non_critical_min_interval_ms", 0) or 0)

        if (
            request.method == "GET"
            and is_degrade
            and min_interval_ms > 0
            and _is_non_critical_path(path)
            and not _is_essential_path(path)
        ):
            client_ip = get_client_ip(request)
            bucket_seconds = max(1, int(min_interval_ms / 1000))
            throttle_key = _build_throttle_key(client_ip, path)
            try:
                redis = await get_redis()
                allowed = await redis.set(
                    throttle_key,
                    "1",
                    ex=bucket_seconds,
                    nx=True,
                )
                if not allowed:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": {
                                "type": "degrade_mode_throttle",
                                "message": "Sistem sedang dalam mode proteksi trafik puncak, coba lagi beberapa saat.",
                                "retry_after_seconds": bucket_seconds,
                            }
                        },
                        headers={
                            "Retry-After": str(bucket_seconds),
                            "X-Degrade-Mode": "true",
                        },
                    )
            except Exception as exc:
                # Fail-open: do not block traffic if Redis is unavailable.
                logger.warning("Degrade mode throttle check skipped: %s", exc)

        response = await call_next(request)
        response.headers["X-Degrade-Mode"] = "true" if is_degrade else "false"
        return response
