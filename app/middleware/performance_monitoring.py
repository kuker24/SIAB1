"""
Performance monitoring middleware for API endpoints.
Logs request duration and tracks slow queries.
"""
import asyncio
import time
import logging
import os
import random
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

from app.api.metrics import record_request as record_prometheus_request
from app.core.runtime_telemetry import (
    canonicalize_endpoint,
    classify_runtime_event,
    record_http_request,
    record_runtime_event,
)

logger = logging.getLogger(__name__)


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """Middleware to monitor API endpoint performance."""

    # Keep telemetry always-on, but avoid excessive warning logs under heavy monitoring traffic.
    SLOW_REQUEST_THRESHOLD_MS = float(os.getenv("SLOW_REQUEST_THRESHOLD_MS", "3000"))
    SLOW_LOG_EXCLUDE_PREFIXES = ("/api/monitoring", "/static/", "/health")
    TELEMETRY_EXCLUDE_PREFIXES = (
        "/static/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/api/monitoring/system/",
    )
    TELEMETRY_PRIORITY_PREFIXES = ("/api/exams/", "/api/auth/", "/ws/")
    TELEMETRY_SAMPLE_RATE = min(
        1.0,
        max(0.0, float(os.getenv("RUNTIME_TELEMETRY_SAMPLE_RATE", "0.20"))),
    )
    TELEMETRY_MAX_IN_FLIGHT = max(
        50,
        int(os.getenv("RUNTIME_TELEMETRY_MAX_IN_FLIGHT", "300")),
    )
    _telemetry_in_flight = 0

    @classmethod
    def _should_record_telemetry(cls, path: str, status_code: int) -> bool:
        if path.startswith(cls.TELEMETRY_EXCLUDE_PREFIXES):
            return False
        if status_code >= 500:
            return True
        if path.startswith(cls.TELEMETRY_PRIORITY_PREFIXES):
            return True
        return random.random() < cls.TELEMETRY_SAMPLE_RATE

    @classmethod
    def _schedule_non_blocking(cls, coro) -> None:
        """
        Fire-and-forget task with a hard cap to avoid unbounded background backlog.
        """
        if cls._telemetry_in_flight >= cls.TELEMETRY_MAX_IN_FLIGHT:
            return

        cls._telemetry_in_flight += 1

        async def _runner():
            try:
                await coro
            finally:
                cls._telemetry_in_flight = max(0, cls._telemetry_in_flight - 1)

        asyncio.create_task(_runner())

    async def dispatch(self, request: Request, call_next: Callable):
        """Monitor request duration and log slow requests."""
        start_time = time.perf_counter()
        path = request.url.path

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            prometheus_endpoint = canonicalize_endpoint(path)
            if prometheus_endpoint:
                record_prometheus_request(
                    request.method,
                    prometheus_endpoint,
                    500,
                    duration_ms / 1000.0,
                )
            # Keep telemetry non-blocking and fail-open with bounded task fan-out.
            if self._should_record_telemetry(path, 500):
                self._schedule_non_blocking(record_http_request(path, 500, duration_ms))
            event_name = classify_runtime_event(str(exc))
            if event_name:
                self._schedule_non_blocking(record_runtime_event(event_name))
            raise

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Keep Prometheus label cardinality bounded to known runtime endpoints.
        prometheus_endpoint = canonicalize_endpoint(path)
        if prometheus_endpoint:
            record_prometheus_request(
                request.method,
                prometheus_endpoint,
                response.status_code,
                duration_ms / 1000.0,
            )

        # Record runtime telemetry (rolling 5xx + latency windows) with sampling and caps
        # to prevent Redis/event-loop amplification under traffic spikes.
        if self._should_record_telemetry(path, response.status_code):
            self._schedule_non_blocking(
                record_http_request(path, response.status_code, duration_ms)
            )

        # Log slow requests
        if duration_ms > self.SLOW_REQUEST_THRESHOLD_MS and not path.startswith(
            self.SLOW_LOG_EXCLUDE_PREFIXES
        ):
            logger.warning(
                f"SLOW REQUEST: {request.method} {path} "
                f"took {duration_ms:.2f}ms (threshold: {self.SLOW_REQUEST_THRESHOLD_MS}ms)"
            )

        # Add performance header
        response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

        return response
