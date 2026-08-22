"""
Security middleware for HTTP headers and HTTPS enforcement.
Implements industry-standard security headers to prevent common attacks.
"""
import hashlib
import json
import re
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, RedirectResponse

from app.core.client_ip import get_client_ip
from app.core.redis_pubsub import get_redis


_SIMPLE_BYTE_RANGE_RE = re.compile(r"^bytes=\d{0,20}-\d{0,20}$", re.IGNORECASE)


def _request_is_https(request: Request) -> bool:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    if forwarded_proto:
        return forwarded_proto.lower() == "https"

    forwarded_scheme = (request.headers.get("x-forwarded-scheme") or "").split(",")[0].strip()
    if forwarded_scheme:
        return forwarded_scheme.lower() == "https"

    cf_visitor = request.headers.get("cf-visitor")
    if cf_visitor:
        try:
            payload = json.loads(cf_visitor)
            if str(payload.get("scheme", "")).lower() == "https":
                return True
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return request.url.scheme == "https"


class RangeHeaderGuardMiddleware(BaseHTTPMiddleware):
    """
    Mitigate expensive Range parsing paths by allowing only simple single-byte ranges.

    Any malformed or multi-range header is stripped before it reaches downstream handlers.
    This reduces exposure to known Range parsing DoS vectors in file response handling.
    """

    def __init__(self, app, max_header_length: int = 128):
        super().__init__(app)
        self.max_header_length = max(32, max_header_length)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        range_header = request.headers.get("range")
        if range_header:
            normalized = range_header.strip()
            is_simple_range = (
                len(normalized) <= self.max_header_length
                and "," not in normalized
                and _SIMPLE_BYTE_RANGE_RE.fullmatch(normalized) is not None
            )
            if not is_simple_range:
                request.scope["headers"] = [
                    (key, value)
                    for key, value in request.scope.get("headers", [])
                    if key != b"range"
                ]

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    
    Headers added:
    - X-Frame-Options: Prevents clickjacking
    - X-Content-Type-Options: Prevents MIME sniffing
    - X-XSS-Protection: Enables XSS filter
    - Strict-Transport-Security: Enforces HTTPS
    - Referrer-Policy: Controls referrer information
    - Permissions-Policy: Controls browser features
    - Cross-Origin headers: Additional isolation
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Enable XSS protection (for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Enforce HTTPS for 1 year (only if request is HTTPS)
        if _request_is_https(request):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        
        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Disable potentially dangerous browser features
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Cross-Origin Policies (NEW - Issue #7 fix)
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"  # Allow YouTube popups
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"  # Allow same-site resources
        
        # Content Security Policy (IMPROVED - Issue #2 fix)
        # Removed 'unsafe-eval' for better security
        # Still need 'unsafe-inline' for some legacy scripts, but tightened other rules
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://www.youtube.com https://www.youtube-nocookie.com https://static.cloudflareinsights.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
            "img-src 'self' data: https: blob:; "
            "frame-src 'self' https://www.youtube.com https://youtube.com https://www.youtube-nocookie.com https://youtu.be blob:; "
            "media-src 'self' https: data: blob:; "
            "connect-src 'self' wss: ws: https://*.googleapis.com https://cdn.jsdelivr.net https://timeapi.io https://cloudflareinsights.com; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none';"
        )
        
        return response


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Redirect all HTTP requests to HTTPS in production.
    
    Set FORCE_HTTPS=true in environment to enable this middleware.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check if we should enforce HTTPS
        import os
        force_https = os.getenv("FORCE_HTTPS", "false").lower() == "true"
        
        if force_https and request.url.scheme == "http":
            # Redirect to HTTPS
            url = request.url.replace(scheme="https")
            return RedirectResponse(url=str(url), status_code=301)
        
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global rate limiting middleware.
    
    Limits:
    - 1000 requests per minute (general)
    - 300 requests per minute for write operations
    - 2000 requests per minute for login endpoint
    
    Uses in-memory storage and identity-aware keys to reduce CGNAT false positives.
    """
    
    def __init__(
        self,
        app,
        max_requests: int = 1000,
        max_write_requests: int = 300,
        login_write_requests: int = 2000,
        window_seconds: int = 60
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.max_write_requests = max_write_requests
        self.login_write_requests = login_write_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, deque[float]] = defaultdict(deque)
        self._last_cleanup_ts: float = 0.0
        # Run global cleanup at least every 30s to prevent key buildup.
        self._cleanup_interval_seconds: float = 30.0
    
    def _clean_old_requests(self, identifier: str, current_time: float):
        """Remove requests older than the time window"""
        entries = self.requests.get(identifier)
        if not entries:
            return

        cutoff_time = current_time - self.window_seconds
        while entries and entries[0] <= cutoff_time:
            entries.popleft()
        if not entries:
            self.requests.pop(identifier, None)

    def _prune_stale_identifiers(self, current_time: float) -> None:
        """
        Global cleanup so identifiers that no longer receive traffic are
        eventually removed from memory.
        """
        cutoff_time = current_time - self.window_seconds
        stale_keys = []
        for identifier, entries in self.requests.items():
            while entries and entries[0] <= cutoff_time:
                entries.popleft()
            if not entries:
                stale_keys.append(identifier)

        for identifier in stale_keys:
            self.requests.pop(identifier, None)
    
    def _get_request_count(self, identifier: str, current_time: float) -> int:
        """Get total request count within time window"""
        entries = self.requests.get(identifier)
        if not entries:
            return 0
        return len(entries)

    async def _check_redis_limit(
        self,
        *,
        identifier: str,
        scope: str,
        limit: int,
        current_time: float,
        request_nonce: str,
    ) -> tuple[bool, int]:
        redis = await get_redis()
        key = f"ratelimit:middleware:{scope}:{identifier}"
        window_start = current_time - self.window_seconds
        request_member = f"{current_time:.6f}:{scope}:{identifier}:{request_nonce}"

        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.zadd(key, {request_member: current_time})
        pipe.expire(key, self.window_seconds + 1)
        results = await pipe.execute()
        current_count = int(results[1] or 0)
        allowed = current_count < limit
        remaining = max(0, limit - current_count - 1) if allowed else 0
        return allowed, remaining

    def _check_local_limit(
        self,
        *,
        identifier: str,
        limit: int,
        current_time: float,
    ) -> tuple[bool, int]:
        self._clean_old_requests(identifier, current_time)
        request_count = self._get_request_count(identifier, current_time)
        if request_count >= limit:
            return False, 0
        self.requests[identifier].append(current_time)
        return True, max(0, limit - request_count - 1)

    @staticmethod
    def _token_fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _is_login_path(path: str) -> bool:
        return path.startswith("/api/auth/login") or path.startswith("/api/auth/signin")

    def _build_identifier(
        self,
        request: Request,
        client_ip: str,
        login_username: str | None = None
    ) -> str:
        """
        Build a stable key that prefers authenticated identity over raw IP.
        This prevents shared-IP (CGNAT/school network) clients from blocking each other.
        """
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                return f"token:{self._token_fingerprint(token)}"

        access_cookie = request.cookies.get("access_token")
        if access_cookie:
            return f"cookie:{self._token_fingerprint(access_cookie)}"

        build_token = request.headers.get("X-Build-Token")
        if build_token:
            return f"build:{self._token_fingerprint(build_token)}"

        # Login is unauthenticated; add UA fingerprint to reduce collision.
        if self._is_login_path(request.url.path):
            if login_username:
                return f"login:{client_ip}:{login_username}"
            user_agent = request.headers.get("user-agent", "")
            if user_agent:
                return f"login:{client_ip}:{self._token_fingerprint(user_agent)}"

        return f"ip:{client_ip}"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import time
        
        # Get client identity
        client_ip = get_client_ip(request)
        login_username: str | None = None

        # For login requests, include username to avoid shared-IP false 429.
        if request.method == "POST" and self._is_login_path(request.url.path):
            try:
                payload = await request.json()
                raw_username = str(payload.get("username", "")).strip().lower()
                if raw_username:
                    login_username = raw_username
            except (json.JSONDecodeError, ValueError, TypeError):
                login_username = None

        identifier = self._build_identifier(request, client_ip, login_username)
        current_time = time.time()
        request_nonce = str(time.time_ns())

        # Periodic global cleanup to avoid unbounded dict growth.
        if current_time - self._last_cleanup_ts >= self._cleanup_interval_seconds:
            self._prune_stale_identifiers(current_time)
            self._last_cleanup_ts = current_time
        
        # Check rate limit
        # Stricter limit for write operations
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            if self._is_login_path(request.url.path):
                # High burst for exam-day mass login traffic.
                limit = self.login_write_requests
                scope = "login"
            else:
                limit = self.max_write_requests
                scope = "write"
        else:
            limit = self.max_requests  # 1000 reads per minute
            scope = "read"

        try:
            is_allowed, remaining = await self._check_redis_limit(
                identifier=identifier,
                scope=scope,
                limit=limit,
                current_time=current_time,
                request_nonce=request_nonce,
            )
        except Exception:
            is_allowed, remaining = self._check_local_limit(
                identifier=identifier,
                limit=limit,
                current_time=current_time,
            )

        if not is_allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Terlalu banyak request. Coba lagi dalam beberapa menit.",
                    "retry_after": self.window_seconds
                },
                headers={"Retry-After": str(self.window_seconds)}
            )

        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(current_time + self.window_seconds))
        
        return response
