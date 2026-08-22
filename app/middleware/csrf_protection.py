"""
CSRF Protection Middleware.

Provides Double-Submit Cookie pattern for CSRF protection on:
- POST/PUT/PATCH/DELETE requests
- Admin panel forms
- Sensitive operations

Note: API endpoints with Bearer tokens are exempt (stateless auth).
"""
import secrets
import hashlib
import hmac
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# CSRF token settings
CSRF_TOKEN_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_COOKIE_NAME = "csrf_cookie"
CSRF_TOKEN_LENGTH = 64
CSRF_TOKEN_EXPIRY_HOURS = 24


class CSRFMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection using Double-Submit Cookie pattern.

    How it works:
    1. Server sets a CSRF token in a cookie (csrf_cookie)
    2. Frontend reads cookie and includes token in header (X-CSRF-Token)
    3. Server validates that header matches cookie

    Exempt from CSRF:
    - GET, HEAD, OPTIONS requests (safe methods)
    - Requests with Bearer authorization (API clients)
    - Paths configured in exempt_paths
    """

    def __init__(
        self,
        app,
        secret_key: str,
        exempt_paths: Optional[list] = None,
        secure_cookie: bool = True
    ):
        super().__init__(app)
        self.secret_key = secret_key.encode()
        self.exempt_paths = exempt_paths or []
        self.secure_cookie = secure_cookie

    async def dispatch(self, request: Request, call_next):
        # Safe methods don't need CSRF protection
        if request.method in ("GET", "HEAD", "OPTIONS"):
            response = await call_next(request)
            # Set CSRF cookie on GET requests (for forms)
            if not request.cookies.get(CSRF_COOKIE_NAME):
                response = self._set_csrf_cookie(response)
            return response

        # Skip CSRF for API routes with Bearer auth (stateless)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)

        # Skip exempt paths
        path = request.url.path
        for exempt in self.exempt_paths:
            if path.startswith(exempt):
                return await call_next(request)

        # Validate CSRF token
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        header_token = request.headers.get(CSRF_HEADER_NAME)

        # Also check form data for non-AJAX requests
        if not header_token:
            try:
                form = await request.form()
                header_token = form.get(CSRF_TOKEN_NAME)
            except Exception as exc:
                logger.debug(
                    "Failed to parse form body for CSRF token on %s: %s",
                    request.url.path,
                    str(exc),
                    exc_info=True,
                )

        if not cookie_token or not header_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token tidak ditemukan"
            )

        if not self._validate_token(cookie_token, header_token):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token tidak valid"
            )

        return await call_next(request)

    def _generate_token(self) -> str:
        """Generate a signed CSRF token."""
        token = secrets.token_urlsafe(CSRF_TOKEN_LENGTH)
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        data = f"{token}:{timestamp}"
        signature = hmac.new(self.secret_key, data.encode(), hashlib.sha256).hexdigest()
        return f"{token}:{timestamp}:{signature}"

    def _validate_token(self, cookie_token: str, header_token: str) -> bool:
        """Validate CSRF token."""
        # Simple comparison for double-submit cookie
        if not hmac.compare_digest(cookie_token, header_token):
            return False

        try:
            parts = cookie_token.split(":")
            if len(parts) != 3:
                return False

            token, timestamp, signature = parts

            # Verify signature
            data = f"{token}:{timestamp}"
            expected_sig = hmac.new(self.secret_key, data.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected_sig):
                return False

            # Check expiry
            token_time = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            if datetime.now(timezone.utc) - token_time > timedelta(hours=CSRF_TOKEN_EXPIRY_HOURS):
                return False

            return True
        except:
            return False

    def _set_csrf_cookie(self, response: Response) -> Response:
        """Set CSRF token cookie on response."""
        token = self._generate_token()
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=token,
            max_age=CSRF_TOKEN_EXPIRY_HOURS * 3600,
            httponly=False,  # JavaScript needs to read this
            secure=self.secure_cookie,
            samesite="lax"
        )
        return response


def get_csrf_token(request: Request) -> str:
    """Get CSRF token from request cookie (for template context)."""
    return request.cookies.get(CSRF_COOKIE_NAME, "")


def csrf_input() -> str:
    """Generate hidden input HTML for CSRF token in forms."""
    return f'<input type="hidden" name="{CSRF_TOKEN_NAME}" id="{CSRF_TOKEN_NAME}">'


def csrf_meta() -> str:
    """Generate meta tag for CSRF token (for JavaScript)."""
    return f'<meta name="{CSRF_TOKEN_NAME}" content="">'
