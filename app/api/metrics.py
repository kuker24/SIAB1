"""
Prometheus Metrics Endpoint
Exposes application metrics for monitoring
"""
import hmac
import os

from fastapi import APIRouter, Response, Request, HTTPException
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)

router = APIRouter()


def _get_metrics_access_config() -> tuple[str, bool]:
    token = os.getenv("METRICS_BEARER_TOKEN", "").strip()
    allow_unauthenticated = (
        os.getenv("METRICS_ALLOW_UNAUTHENTICATED", "false").strip().lower() == "true"
    )
    return token, allow_unauthenticated

# Create a custom registry
registry = CollectorRegistry()

# Metrics
REQUEST_COUNT = Counter(
    'fastapi_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=registry
)

REQUEST_DURATION = Histogram(
    'fastapi_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    registry=registry
)

ACTIVE_SESSIONS = Gauge(
    'fastapi_active_exam_sessions',
    'Number of active exam sessions',
   registry=registry
)

ACTIVE_USERS = Gauge(
    'fastapi_active_users',
    'Number of active users',
    registry=registry
)

ERROR_COUNT = Counter(
    'fastapi_errors_total',
    'Total application errors',
    ['error_type'],
    registry=registry
)

DB_CONNECTIONS = Gauge(
    'fastapi_db_connections',
    'Active database connections',
    registry=registry
)

REDIS_HITS = Counter(
    'fastapi_redis_cache_hits',
    'Redis cache hits',
    registry=registry
)

REDIS_MISSES = Counter(
    'fastapi_redis_cache_misses',
    'Redis cache misses',
    registry=registry
)


@router.get("/metrics")
async def metrics(request: Request):
    """
    Prometheus metrics endpoint
    Returns metrics in Prometheus format
    """
    metrics_token, allow_unauthenticated = _get_metrics_access_config()

    if metrics_token:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing metrics bearer token")
        provided = auth_header[7:].strip()
        if not hmac.compare_digest(provided, metrics_token):
            raise HTTPException(status_code=401, detail="Invalid metrics bearer token")
    elif not allow_unauthenticated:
        # Secure-by-default: metrics stays dark unless explicitly configured.
        raise HTTPException(status_code=404, detail="Not found")

    output_registry = registry
    if os.getenv("PROMETHEUS_MULTIPROC_DIR", "").strip():
        # Build a fresh registry per scrape to avoid duplicate collectors.
        output_registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(output_registry)

    return Response(
        content=generate_latest(output_registry),
        media_type=CONTENT_TYPE_LATEST
    )


# Helper functions to update metrics
def record_request(method: str, endpoint: str, status: int, duration: float):
    """Record HTTP request metrics"""
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
    REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)


def record_error(error_type: str):
    """Record error metrics"""
    ERROR_COUNT.labels(error_type=error_type).inc()


def update_active_sessions(count: int):
    """Update active exam sessions gauge"""
    ACTIVE_SESSIONS.set(count)


def update_active_users(count: int):
    """Update active users gauge"""
    ACTIVE_USERS.set(count)


def update_db_connections(count: int):
    """Update database connections gauge"""
    DB_CONNECTIONS.set(count)


def record_cache_hit():
    """Record Redis cache hit"""
    REDIS_HITS.inc()


def record_cache_miss():
    """Record Redis cache miss"""
    REDIS_MISSES.inc()
