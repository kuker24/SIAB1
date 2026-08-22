"""
HTTP Request/Response Logging Middleware

Logs all HTTP requests with unique request IDs for tracing.
Part of Phase 5: Centralized Logging
"""
import time
import uuid
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.client_ip import get_client_ip

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all HTTP requests and responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID
        request_id = str(uuid.uuid4())[:8]

        # Attach to request state for downstream use
        request.state.request_id = request_id

        # Extract request details
        client_ip = get_client_ip(request)
        method = request.method
        path = request.url.path
        user_agent = request.headers.get("user-agent", "unknown")[:100]
        is_noise_path = (
            path.startswith("/static/")
            or path == "/health"
            or path == "/favicon.ico"
        )

        # Log request start
        start_time = time.time()

        if not is_noise_path:
            logger.debug(
                "Request started",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "client_ip": client_ip,
                    "user_agent": user_agent
                }
            )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log response
            log_level = logging.INFO
            if response.status_code >= 500:
                log_level = logging.ERROR
            elif response.status_code == 429:
                # Keep rate-limit visibility as warning signal.
                log_level = logging.WARNING
            elif response.status_code >= 400:
                # 4xx can be expected during auth flows; avoid warning noise.
                log_level = logging.INFO

            if (not is_noise_path) or response.status_code >= 400:
                logger.log(
                    log_level,
                    "Request completed",
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "status_code": response.status_code,
                        "duration_ms": round(duration_ms, 2)
                    }
                )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            logger.error(
                f"Request failed: {str(e)}",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "error": str(e),
                    "duration_ms": round(duration_ms, 2)
                },
                exc_info=True
            )
            raise


async def log_requests(request: Request, call_next: Callable) -> Response:
    """Alternative function-based middleware for logging."""
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id

    start_time = time.time()

    response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000

    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} ({duration_ms:.1f}ms)",
        extra={"request_id": request_id}
    )

    response.headers["X-Request-ID"] = request_id
    return response
