"""
Emergency freeze guard middleware.

When freeze mode is enabled, all non-exempt authenticated actions are blocked.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.cache import is_freeze_mode_enabled
from app.core.security import decode_token, is_freeze_exempt_identity

logger = logging.getLogger(__name__)


ALWAYS_ALLOW_EXACT = {
    "/health",
    "/ws/health",
    "/openapi.json",
    "/docs",
    "/redoc",
}

ALWAYS_ALLOW_PREFIXES = (
    "/static/",
    "/admin/",
    "/student/",
    "/seb/",
    "/exam/",
)

FREEZE_LOGIN_ALLOW = {
    "/api/auth/login",
    "/api/auth/signin",
    "/api/auth/control/login",
    "/api/auth/control/signin",
    "/api/auth/admin/login",
    "/api/auth/admin/signin",
    "/api/auth/teacher/login",
    "/api/auth/teacher/signin",
    "/api/auth/pengawas/login",
    "/api/auth/pengawas/signin",
    "/api/auth/student/login",
    "/api/auth/student/signin",
    # Reverse-proxy compatibility paths (before upstream rewrite)
    "/api/control/auth/login",
    "/api/control/auth/signin",
    "/api/admin/auth/login",
    "/api/admin/auth/signin",
    "/api/teacher/auth/login",
    "/api/teacher/auth/signin",
    "/api/pengawas/auth/login",
    "/api/pengawas/auth/signin",
    "/api/student/auth/login",
    "/api/student/auth/signin",
}

FREEZE_LOGIN_PATTERN = re.compile(
    r"^/api/(?:"
    r"auth(?:/(?:control|admin|teacher|pengawas|student))?"
    r"|(?:control|admin|teacher|pengawas|student)/auth"
    r")/(?:login|signin)$"
)


def _is_login_path(path: str) -> bool:
    if path in FREEZE_LOGIN_ALLOW:
        return True
    return bool(FREEZE_LOGIN_PATTERN.match(path))


def _extract_bearer_token(request: Request) -> Optional[str]:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header[7:].strip()
    return token or None


def _is_page_or_static_exempt(path: str) -> bool:
    if path in ALWAYS_ALLOW_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in ALWAYS_ALLOW_PREFIXES)


class FreezeModeGuardMiddleware(BaseHTTPMiddleware):
    """Block non-exempt actions when freeze mode is active."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Always allow preflight to keep browser behavior stable.
        if request.method == "OPTIONS":
            return await call_next(request)

        if _is_page_or_static_exempt(path):
            return await call_next(request)

        try:
            freeze_enabled = await is_freeze_mode_enabled()
        except Exception as exc:
            logger.warning("Freeze mode check failed, fail-open: %s", exc)
            freeze_enabled = False

        if not freeze_enabled:
            return await call_next(request)

        # Allow login endpoints so exempt developer/admin can still authenticate.
        if _is_login_path(path):
            return await call_next(request)

        token = _extract_bearer_token(request)
        if token:
            token_data = decode_token(token, verify_exp=True)
            if token_data and is_freeze_exempt_identity(
                token_data.role,
                token_data.username,
                token_data.job_title,
            ):
                return await call_next(request)

        return JSONResponse(
            status_code=423,
            content={
                "detail": {
                    "type": "freeze_mode",
                    "message": (
                        "Sistem sedang di-freeze oleh developer. "
                        "Semua aktivitas non-developer sementara dikunci."
                    ),
                }
            },
            headers={"X-Freeze-Mode": "true"},
        )
