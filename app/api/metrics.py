"""
Prometheus Metrics Endpoint
Exposes application metrics for monitoring
"""
import atexit
import hmac
import os

from fastapi import APIRouter, HTTPException, Request, Response
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

START_ADMISSION_HOLDERS = Gauge(
    "siab_start_admission_holders",
    "Current START admission permit holders in each worker",
    ["replica"],
    multiprocess_mode="liveall",
    registry=registry,
)

START_ADMISSION_LIMIT = Gauge(
    "siab_start_admission_limit",
    "Configured START admission limit in each worker",
    ["replica"],
    multiprocess_mode="liveall",
    registry=registry,
)

START_ADMISSION_WAITERS = Gauge(
    "siab_start_admission_waiters",
    "Current START admission waiters in each worker",
    ["replica"],
    multiprocess_mode="liveall",
    registry=registry,
)

START_ADMISSION_PEAK_HOLDERS = Gauge(
    "siab_start_admission_peak_holders",
    "Peak START admission permit holders since worker start",
    ["replica"],
    multiprocess_mode="liveall",
    registry=registry,
)

START_ADMISSION_PEAK_WAITERS = Gauge(
    "siab_start_admission_peak_waiters",
    "Peak START admission waiters since worker start",
    ["replica"],
    multiprocess_mode="liveall",
    registry=registry,
)

START_ADMISSION_WAIT = Histogram(
    "siab_start_admission_wait_seconds",
    "Time spent waiting for a START admission permit",
    ["replica", "segment"],
    buckets=(
        0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05,
        0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
    ),
    registry=registry,
)

START_ADMISSION_ACQUISITIONS = Counter(
    "siab_start_admission_acquisitions_total",
    "Successful START admission permit acquisitions",
    ["replica", "segment"],
    registry=registry,
)

START_ADMISSION_RELEASES = Counter(
    "siab_start_admission_releases_total",
    "Released START admission permits",
    ["replica", "segment"],
    registry=registry,
)

START_ADMISSION_CANCELLATIONS = Counter(
    "siab_start_admission_cancellations_total",
    "START operations cancelled while waiting or holding a permit",
    ["replica", "phase"],
    registry=registry,
)

START_ADMISSION_FAILURES = Counter(
    "siab_start_admission_failures_total",
    "START admission acquisition failures",
    ["replica", "reason"],
    registry=registry,
)

START_DB_SECTION_DURATION = Histogram(
    "siab_start_db_section_seconds",
    "Duration of bounded START database sections",
    ["replica", "segment"],
    buckets=(
        0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05,
        0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0,
    ),
    registry=registry,
)

_START_SEGMENTS = frozenset({"security", "main", "questions", "integrity"})
_START_REPLICA = (os.getenv("SIAB_REPLICA") or "control").strip() or "control"


def _start_segment(segment: str) -> str:
    return segment if segment in _START_SEGMENTS else "other"


def initialize_start_admission_metrics(limit: int) -> None:
    labels = {"replica": _START_REPLICA}
    START_ADMISSION_LIMIT.labels(**labels).set(limit)
    START_ADMISSION_HOLDERS.labels(**labels).set(0)
    START_ADMISSION_WAITERS.labels(**labels).set(0)
    START_ADMISSION_PEAK_HOLDERS.labels(**labels).set(0)
    START_ADMISSION_PEAK_WAITERS.labels(**labels).set(0)


def update_start_admission_metrics(
    *,
    holders: int,
    waiters: int,
    peak_holders: int,
    peak_waiters: int,
) -> None:
    labels = {"replica": _START_REPLICA}
    START_ADMISSION_HOLDERS.labels(**labels).set(holders)
    START_ADMISSION_WAITERS.labels(**labels).set(waiters)
    START_ADMISSION_PEAK_HOLDERS.labels(**labels).set(peak_holders)
    START_ADMISSION_PEAK_WAITERS.labels(**labels).set(peak_waiters)


def record_start_admission_acquisition(segment: str, wait_seconds: float) -> None:
    labels = {"replica": _START_REPLICA, "segment": _start_segment(segment)}
    START_ADMISSION_ACQUISITIONS.labels(**labels).inc()
    START_ADMISSION_WAIT.labels(**labels).observe(max(0.0, wait_seconds))


def record_start_admission_release(segment: str) -> None:
    START_ADMISSION_RELEASES.labels(
        replica=_START_REPLICA,
        segment=_start_segment(segment),
    ).inc()


def record_start_admission_cancellation(phase: str) -> None:
    START_ADMISSION_CANCELLATIONS.labels(
        replica=_START_REPLICA,
        phase=phase if phase in {"waiting", "holding"} else "other",
    ).inc()


def record_start_admission_failure(reason: str) -> None:
    START_ADMISSION_FAILURES.labels(
        replica=_START_REPLICA,
        reason=reason if reason in {"timeout", "error"} else "other",
    ).inc()


def record_start_db_section(segment: str, duration_seconds: float) -> None:
    START_DB_SECTION_DURATION.labels(
        replica=_START_REPLICA,
        segment=_start_segment(segment),
    ).observe(max(0.0, duration_seconds))


def _mark_prometheus_process_dead() -> None:
    try:
        multiprocess.mark_process_dead(os.getpid())
    except OSError:
        pass


if os.getenv("PROMETHEUS_MULTIPROC_DIR", "").strip():
    atexit.register(_mark_prometheus_process_dead)


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
