"""
Runtime telemetry utilities for rolling HTTP and event metrics.

Stored in Redis short windows for:
- global + lane 5xx rates
- critical endpoint latency percentiles (p95 + p99)
- lane latency percentiles (student/admin/shared)
- runtime error spikes
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Optional
from uuid import uuid4

from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)


GLOBAL_REQUEST_KEY = "runtime:http:global:requests"
GLOBAL_5XX_KEY = "runtime:http:global:5xx"
LATENCY_KEY_PREFIX = "runtime:http:latency"
REQUEST_KEY_PREFIX = "runtime:http:requests"
REQUEST_5XX_KEY_PREFIX = "runtime:http:requests:5xx"
EVENT_KEY_PREFIX = "runtime:event"

LANE_REQUEST_KEY_PREFIX = "runtime:http:lane:requests"
LANE_5XX_KEY_PREFIX = "runtime:http:lane:requests:5xx"
LANE_LATENCY_KEY_PREFIX = "runtime:http:lane:latency"

RETENTION_SECONDS = 900  # 15 minutes


CRITICAL_ENDPOINT_PATTERNS: tuple[tuple[str, Any], ...] = (
    ("auth_signin", re.compile(r"^/api/auth/(signin|login)$")),
    ("exam_start", re.compile(r"^/api/exams/\d+/start$")),
    ("submit_answer", re.compile(r"^/api/exams/submit-answer$")),
    ("exam_submit", re.compile(r"^/api/exams/submit$")),
)

STUDENT_LANE_PREFIXES = (
    "/api/exams",
    "/api/exam",
    "/api/sxb",
    "/api/seb",
    "/student",
)
ADMIN_LANE_PREFIXES = (
    "/api/monitoring",
    "/api/users",
    "/api/system",
    "/api/settings",
    "/api/activity",
    "/api/analytics",
    "/api/questions",
    "/api/templates",
    "/api/grading",
    "/api/security",
    "/api/backup",
    "/api/alerts",
    "/admin",
)
RUNTIME_LANES = ("student", "admin", "shared")


def _now_ms() -> int:
    return int(time.time() * 1000)


def canonicalize_endpoint(path: str) -> Optional[str]:
    for endpoint_key, pattern in CRITICAL_ENDPOINT_PATTERNS:
        if isinstance(pattern, str):
            if path == pattern:
                return endpoint_key
        elif pattern.match(path):
            return endpoint_key
    return None


def classify_runtime_lane(path: str) -> str:
    normalized = str(path or "").strip().lower()
    if normalized.startswith(STUDENT_LANE_PREFIXES):
        return "student"
    if normalized.startswith(ADMIN_LANE_PREFIXES):
        return "admin"
    return "shared"


def classify_runtime_event(error_message: str) -> Optional[str]:
    lowered = (error_message or "").lower()
    if not lowered:
        return None
    if "queuepool" in lowered and "timeout" in lowered:
        return "db_pool_timeout"
    if "redis" in lowered and "timeout" in lowered:
        return "redis_timeout"
    if "timeouterror" in lowered and "redis" in lowered:
        return "redis_timeout"
    return None


async def record_runtime_event(event_name: str) -> None:
    if not event_name:
        return
    now_ms = _now_ms()
    key = f"{EVENT_KEY_PREFIX}:{event_name}"
    member = f"{now_ms}:{uuid4().hex}"
    min_score = now_ms - (RETENTION_SECONDS * 1000)
    try:
        redis = await get_redis()
        pipe = redis.pipeline()
        pipe.zadd(key, {member: now_ms})
        pipe.zremrangebyscore(key, 0, min_score)
        pipe.expire(key, RETENTION_SECONDS + 60)
        await pipe.execute()
    except Exception as exc:
        logger.debug("Failed to record runtime event %s: %s", event_name, exc)


async def get_runtime_event_rate(event_name: str, window_seconds: int = 60) -> float:
    if not event_name:
        return 0.0
    now_ms = _now_ms()
    min_score = now_ms - (window_seconds * 1000)
    key = f"{EVENT_KEY_PREFIX}:{event_name}"
    try:
        redis = await get_redis()
        count = await redis.zcount(key, min_score, now_ms)
        return round((count * 60.0) / max(window_seconds, 1), 2)
    except Exception as exc:
        logger.debug("Failed to compute runtime event rate for %s: %s", event_name, exc)
        return 0.0


async def record_http_request(path: str, status_code: int, duration_ms: float) -> None:
    """
    Record HTTP status/latency into Redis rolling windows.
    """
    now_ms = _now_ms()
    min_score = now_ms - (RETENTION_SECONDS * 1000)
    request_id = uuid4().hex

    global_member = f"{now_ms}|{status_code}|{request_id}"
    global_5xx_member = f"{now_ms}|{request_id}"

    endpoint_key = canonicalize_endpoint(path)
    endpoint_member = f"{now_ms}|{request_id}"
    latency_member = f"{now_ms}|{float(duration_ms):.3f}|{request_id}"

    lane = classify_runtime_lane(path)
    lane_request_key = f"{LANE_REQUEST_KEY_PREFIX}:{lane}"
    lane_error_key = f"{LANE_5XX_KEY_PREFIX}:{lane}"
    lane_latency_key = f"{LANE_LATENCY_KEY_PREFIX}:{lane}"

    try:
        redis = await get_redis()
        pipe = redis.pipeline()

        pipe.zadd(GLOBAL_REQUEST_KEY, {global_member: now_ms})
        pipe.zremrangebyscore(GLOBAL_REQUEST_KEY, 0, min_score)
        pipe.expire(GLOBAL_REQUEST_KEY, RETENTION_SECONDS + 60)

        if status_code >= 500:
            pipe.zadd(GLOBAL_5XX_KEY, {global_5xx_member: now_ms})
            pipe.zremrangebyscore(GLOBAL_5XX_KEY, 0, min_score)
            pipe.expire(GLOBAL_5XX_KEY, RETENTION_SECONDS + 60)

        pipe.zadd(lane_request_key, {endpoint_member: now_ms})
        pipe.zadd(lane_latency_key, {latency_member: now_ms})
        pipe.zremrangebyscore(lane_request_key, 0, min_score)
        pipe.zremrangebyscore(lane_latency_key, 0, min_score)
        pipe.expire(lane_request_key, RETENTION_SECONDS + 60)
        pipe.expire(lane_latency_key, RETENTION_SECONDS + 60)
        if status_code >= 500:
            pipe.zadd(lane_error_key, {endpoint_member: now_ms})
            pipe.zremrangebyscore(lane_error_key, 0, min_score)
            pipe.expire(lane_error_key, RETENTION_SECONDS + 60)

        if endpoint_key:
            request_key = f"{REQUEST_KEY_PREFIX}:{endpoint_key}"
            endpoint_latency_key = f"{LATENCY_KEY_PREFIX}:{endpoint_key}"

            pipe.zadd(request_key, {endpoint_member: now_ms})
            pipe.zadd(endpoint_latency_key, {latency_member: now_ms})
            pipe.zremrangebyscore(request_key, 0, min_score)
            pipe.zremrangebyscore(endpoint_latency_key, 0, min_score)
            pipe.expire(request_key, RETENTION_SECONDS + 60)
            pipe.expire(endpoint_latency_key, RETENTION_SECONDS + 60)

            if status_code >= 500:
                endpoint_5xx_key = f"{REQUEST_5XX_KEY_PREFIX}:{endpoint_key}"
                pipe.zadd(endpoint_5xx_key, {endpoint_member: now_ms})
                pipe.zremrangebyscore(endpoint_5xx_key, 0, min_score)
                pipe.expire(endpoint_5xx_key, RETENTION_SECONDS + 60)

        await pipe.execute()
    except Exception as exc:
        logger.debug("Failed to record HTTP runtime telemetry: %s", exc)


async def _count_requests(
    window_seconds: int,
    *,
    endpoint_key: Optional[str] = None,
) -> tuple[int, int]:
    now_ms = _now_ms()
    min_score = now_ms - (window_seconds * 1000)
    if endpoint_key:
        total_key = f"{REQUEST_KEY_PREFIX}:{endpoint_key}"
        error_key = f"{REQUEST_5XX_KEY_PREFIX}:{endpoint_key}"
    else:
        total_key = GLOBAL_REQUEST_KEY
        error_key = GLOBAL_5XX_KEY
    try:
        redis = await get_redis()
        total = await redis.zcount(total_key, min_score, now_ms)
        errors = await redis.zcount(error_key, min_score, now_ms)
        return int(total), int(errors)
    except Exception as exc:
        logger.debug("Failed to count runtime requests: %s", exc)
        return 0, 0


async def _count_lane_requests(
    lane: str,
    window_seconds: int,
) -> tuple[int, int]:
    normalized_lane = str(lane or "").strip().lower()
    if normalized_lane not in RUNTIME_LANES:
        return 0, 0
    now_ms = _now_ms()
    min_score = now_ms - (window_seconds * 1000)
    try:
        redis = await get_redis()
        total = await redis.zcount(f"{LANE_REQUEST_KEY_PREFIX}:{normalized_lane}", min_score, now_ms)
        errors = await redis.zcount(f"{LANE_5XX_KEY_PREFIX}:{normalized_lane}", min_score, now_ms)
        return int(total), int(errors)
    except Exception as exc:
        logger.debug("Failed to count lane requests for %s: %s", normalized_lane, exc)
        return 0, 0


async def get_5xx_rate_percent(
    window_seconds: int = 60,
    *,
    endpoint_key: Optional[str] = None,
) -> float:
    total, errors = await _count_requests(window_seconds, endpoint_key=endpoint_key)
    if total <= 0:
        return 0.0
    return round((errors / total) * 100.0, 3)


async def get_lane_5xx_rate_percent(lane: str, window_seconds: int = 60) -> float:
    total, errors = await _count_lane_requests(lane, window_seconds)
    if total <= 0:
        return 0.0
    return round((errors / total) * 100.0, 3)


def _parse_latency_member(raw_member: str) -> Optional[float]:
    try:
        _, duration_ms, _ = raw_member.split("|", 2)
        return float(duration_ms)
    except Exception:
        return None


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = max(0.0, min(1.0, percentile)) * (len(sorted_values) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return float(sorted_values[lower])
    weight = rank - lower
    return float(sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight)


async def _compute_latency_percentile(
    key: str,
    *,
    percentile: float,
    window_seconds: int,
) -> float:
    now_ms = _now_ms()
    min_score = now_ms - (window_seconds * 1000)
    try:
        redis = await get_redis()
        members = await redis.zrangebyscore(key, min_score, now_ms)
        latencies: list[float] = []
        for member in members:
            raw = member.decode("utf-8", errors="ignore") if isinstance(member, bytes) else str(member)
            value = _parse_latency_member(raw)
            if value is not None:
                latencies.append(value)
        if not latencies:
            return 0.0
        latencies.sort()
        return round(_percentile(latencies, percentile), 2)
    except Exception as exc:
        logger.debug("Failed to compute latency percentile for %s: %s", key, exc)
        return 0.0


async def compute_endpoint_percentile_latency_ms(
    endpoint_key: str,
    *,
    percentile: float,
    window_seconds: int = 180,
) -> float:
    if not endpoint_key:
        return 0.0
    return await _compute_latency_percentile(
        f"{LATENCY_KEY_PREFIX}:{endpoint_key}",
        percentile=percentile,
        window_seconds=window_seconds,
    )


async def compute_endpoint_p95_latency_ms(endpoint_key: str, window_seconds: int = 180) -> float:
    return await compute_endpoint_percentile_latency_ms(
        endpoint_key,
        percentile=0.95,
        window_seconds=window_seconds,
    )


async def compute_endpoint_p99_latency_ms(endpoint_key: str, window_seconds: int = 180) -> float:
    return await compute_endpoint_percentile_latency_ms(
        endpoint_key,
        percentile=0.99,
        window_seconds=window_seconds,
    )


async def compute_lane_latency_percentile_ms(
    lane: str,
    *,
    percentile: float = 0.95,
    window_seconds: int = 180,
) -> float:
    normalized_lane = str(lane or "").strip().lower()
    if normalized_lane not in RUNTIME_LANES:
        return 0.0
    return await _compute_latency_percentile(
        f"{LANE_LATENCY_KEY_PREFIX}:{normalized_lane}",
        percentile=percentile,
        window_seconds=window_seconds,
    )


async def get_runtime_snapshot(
    window_seconds: int = 60,
    latency_window_seconds: int = 180,
) -> Dict[str, Any]:
    total, errors = await _count_requests(window_seconds)
    global_rate = round((errors / total * 100.0), 3) if total else 0.0

    critical: Dict[str, Dict[str, Any]] = {}
    for endpoint_key, _ in CRITICAL_ENDPOINT_PATTERNS:
        endpoint_total, endpoint_errors = await _count_requests(
            window_seconds,
            endpoint_key=endpoint_key,
        )
        endpoint_rate = (
            round((endpoint_errors / endpoint_total * 100.0), 3)
            if endpoint_total
            else 0.0
        )
        p95_latency = await compute_endpoint_p95_latency_ms(
            endpoint_key,
            window_seconds=latency_window_seconds,
        )
        p99_latency = await compute_endpoint_p99_latency_ms(
            endpoint_key,
            window_seconds=latency_window_seconds,
        )
        critical[endpoint_key] = {
            "requests": endpoint_total,
            "errors_5xx": endpoint_errors,
            "error_rate_percent": endpoint_rate,
            "p95_latency_ms": p95_latency,
            "p99_latency_ms": p99_latency,
        }

    lanes: Dict[str, Dict[str, float | int]] = {}
    for lane in RUNTIME_LANES:
        lane_total, lane_errors = await _count_lane_requests(lane, window_seconds)
        lane_rate = round((lane_errors / lane_total * 100.0), 3) if lane_total else 0.0
        lane_p95 = await compute_lane_latency_percentile_ms(
            lane,
            percentile=0.95,
            window_seconds=latency_window_seconds,
        )
        lane_p99 = await compute_lane_latency_percentile_ms(
            lane,
            percentile=0.99,
            window_seconds=latency_window_seconds,
        )
        lanes[lane] = {
            "requests": lane_total,
            "errors_5xx": lane_errors,
            "error_rate_percent": lane_rate,
            "p95_latency_ms": lane_p95,
            "p99_latency_ms": lane_p99,
        }

    return {
        "window_seconds": window_seconds,
        "latency_window_seconds": latency_window_seconds,
        "global": {
            "requests": total,
            "errors_5xx": errors,
            "error_rate_percent": global_rate,
        },
        "critical_endpoints": critical,
        "lanes": lanes,
        "event_rates_per_min": {
            "db_pool_timeout": await get_runtime_event_rate("db_pool_timeout", window_seconds),
            "redis_timeout": await get_runtime_event_rate("redis_timeout", window_seconds),
        },
    }
