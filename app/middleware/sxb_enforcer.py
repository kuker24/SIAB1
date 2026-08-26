"""
SXB Enforcer Middleware
=======================
Middleware to enforce SXB (Secure eXam Browser) client usage for protected paths.

DEVELOPMENT MODE: Set ENFORCE_SXB=false in .env OR enable Developer Mode in settings.
"""
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
import time
import re
import os
import logging


logger = logging.getLogger(__name__)


class SXBEnforcerMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces SXB client usage for protected paths.

    Behavior:
    - If ENFORCE_SXB is False (development): Allow all requests
    - If Developer Mode enabled in settings: Allow all requests
    - If ENFORCE_SXB is True (production) AND Developer Mode OFF: Require SXB-Client or SEB user agent
    """

    def __init__(self, app, enforce_sxb: bool = False):
        super().__init__(app)
        # Read from environment, default to False for development
        env_enforce = os.getenv("ENFORCE_SXB", "false").lower()
        self.enforce_sxb = enforce_sxb or env_enforce == "true"

    async def dispatch(self, request: Request, call_next):
        # ============================================
        # DEVELOPMENT MODE: Skip all checks
        # ============================================
        if not self.enforce_sxb:
            return await call_next(request)

        # ============================================
        # PRODUCTION MODE: Enforce SXB/SEB client
        # ============================================

        # Paths that REQUIRE strict SXB Security (STUDENT ONLY)
        # Admin/Teacher paths are NOT protected - they use normal browser
        # NOTE: Only EXAM PAGE is protected, dashboard/login are accessible from any browser
        protected_paths = [
            re.compile(r"^/student/exam"),       # Student exam page ONLY (requires APK/SEB)
            re.compile(r"^/api/exams/\d+/start"),  # Start exam session
            re.compile(r"^/api/exams/\d+/submit"), # Legacy submit path
            re.compile(r"^/api/exams/submit$"),    # Actual submit endpoint
            re.compile(r"^/api/exams/submit-answer$"), # Actual answer endpoint
            re.compile(r"^/api/exams/auto-save$"),
            re.compile(r"^/api/exams/auto-save-batch$"),
            re.compile(r"^/api/exams/answer-journal/sync$"),
            re.compile(r"^/api/exams/\d+/answer"), # Legacy answer path
            re.compile(r"^/api/sessions/\d+"),     # Student exam sessions
        ]

        # Whitelist (always allow without checks)
        # Includes: Admin pages, API endpoints used by admin/teacher, static files
        white_list = [
            "/static",
            "/admin",
            "/docs",
            "/openapi.json",
            "/health",
            "/api/auth",        # Login for ALL users (admin, teacher, student)
            "/api/exams/join",  # Join exam with token (validated separately by auth)
            "/api/validate-apk-token",  # APK token validation
            "/api/exams/default-seb-config.seb",
            "/api/exams/seb-qrcode",
            "/api/seb",
        ]

        path = request.url.path

        # Skip whitelist
        if any(path.startswith(w) for w in white_list):
            return await call_next(request)

        # Check exact root path
        if path == "/":
            return await call_next(request)

        # Check if path is protected
        is_protected = any(p.match(path) for p in protected_paths)

        # Fast path: do not call Redis/DB flags for non-protected routes.
        if not is_protected:
            return await call_next(request)

        # Check database developer mode setting only for protected routes.
        from app.core.cache import is_developer_mode_enabled
        if await is_developer_mode_enabled():
            return await call_next(request)

        if is_protected:
            user_agent = request.headers.get("user-agent", "").lower()

            # Check for SXB-Client or Safe Exam Browser
            is_sxb = "sxb-client" in user_agent or "exambro" in user_agent
            is_seb = "seb" in user_agent or "safe exam browser" in user_agent

            if not is_sxb and not is_seb:
                # If it's a browser request (HTML), redirect to student dashboard
                accept_header = request.headers.get("accept", "")
                if "text/html" in accept_header:
                    return RedirectResponse(status_code=303, url="/student/dashboard.html")

                # Otherwise (API), block it
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Akses ditolak. Gunakan Aplikasi Ujian (APK) atau Safe Exam Browser."}
                )

            # For SXB clients (Mobile App), logic depends on path
            if is_sxb:
                # 1. API REQUESTS (Login, Submit, Data)
                if path.startswith("/api/"):
                    # Define endpoints that MUST have signature (Native App Calls)
                    # Login, Refresh, and Token Validation happen natively, so they MUST send signature.
                    # Other endpoints (like /api/auth/me, /api/exams) might be called by WebView (AJAX),
                    # so they might not have signature. We rely on Auth Token for those.
                    strict_endpoints = [
                        "/api/auth/login",
                        "/api/auth/signin",
                        "/api/auth/refresh",
                        "/api/validate-apk-token",
                    ]
                    is_strict_path = any(path.startswith(p) for p in strict_endpoints)

                    sig = request.headers.get("X-App-Signature")
                    ts = request.headers.get("X-App-Timestamp")

                    # If Strict Path OR Signature is present, validate it
                    if is_strict_path or sig:
                        if not sig or not ts:
                            # Only block missing headers if it's a strict path
                            if is_strict_path:
                                return JSONResponse(
                                    status_code=403,
                                    content={"detail": "Security Headers Missing. Update your App."}
                                )
                            else:
                                # Non-strict path without headers -> Allow (Auth middleware will handle security)
                                return await call_next(request)

                        # Verify Signature
                        from app.core.cache import get_allowed_signatures
                        db_sigs = await get_allowed_signatures()

                        # STRICT MODE: No signatures configured = Block APK
                        if not db_sigs or all(not s.strip() for s in db_sigs):
                            logger.warning("SXB block: strict mode active but no signatures configured")
                            return JSONResponse(
                                status_code=403,
                                content={"detail": "Sistem APK belum dikonfigurasi. Hubungi admin untuk mengatur App Signatures."}
                            )

                        # Normalize client signature (Remove colons, lower case)
                        normalized_sig = sig.replace(":", "").lower().strip() if sig else ""

                        # ONLY validate against Database signatures
                        # (No hardcoded fallback - Admin Panel is single source of truth)
                        is_valid_sig = False
                        for allowed in db_sigs:
                            if allowed and allowed.strip().lower() == normalized_sig:
                                is_valid_sig = True
                                break

                        if not is_valid_sig:
                            allowed_count = sum(1 for s in db_sigs if s and s.strip())
                            logger.warning(
                                "SXB block: signature mismatch path=%s sig_prefix=%s allowed_count=%s",
                                path,
                                normalized_sig[:12],
                                allowed_count,
                            )
                            return JSONResponse(
                                status_code=403,
                                content={"detail": "Invalid App Signature. Unofficial app detected."}
                            )

                        # Verify Timestamp freshness (Relaxed to 1 hour for bad clocks)
                        try:
                            server_time = int(time.time())
                            client_time = int(ts)
                            diff = abs(server_time - client_time)

                            if diff > 3600: # 1 Hour tolerance
                                logger.warning(
                                    "SXB block: timestamp expired path=%s diff_seconds=%s",
                                    path,
                                    diff,
                                )
                                return JSONResponse(status_code=403, content={"detail": "Request Expired (Check Device Time)"})
                        except Exception as e:
                            logger.warning(
                                "SXB timestamp parse error path=%s value=%s error=%s",
                                path,
                                ts,
                                e,
                            )
                            # Allow if timestamp parsing fails (fail-open).

                # 2. WEBVIEW REQUESTS (/student/...) -> RELAXED SECURITY
                # WebViews cannot easily send custom headers.
                # We rely on the fact that they must have a valid Session Cookie (obtained via strict Login API)
                # So we ONLY check User-Agent here (which is already done by is_sxb check above)
                else:
                    pass

        return await call_next(request)
