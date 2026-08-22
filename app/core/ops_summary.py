"""
Selective operational summary for live monitoring dashboard.

This module intentionally exposes only high-signal, low-noise indicators.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auto_restart import get_auto_restart_schedule, get_auto_restart_status
from app.core.degrade_mode import get_runtime_policy
from app.core.metrics_collector import metrics_collector
from app.core.runtime_telemetry import get_runtime_snapshot


SEV_HEALTHY = 0
SEV_WARNING = 1
SEV_CRITICAL = 2
SEV_UNKNOWN = -1

logger = logging.getLogger(__name__)

_SAFE_HOST_RE = re.compile(r"^(?:\[[0-9a-fA-F:]+\]|[a-zA-Z0-9.-]+)(?::\d{1,5})?$")


_cache_lock = asyncio.Lock()
_cache_payload_by_host: Dict[str, Dict[str, Any]] = {}
_cache_at_monotonic_by_host: Dict[str, float] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _status_from_severity(severity: int) -> str:
    if severity == SEV_CRITICAL:
        return "critical"
    if severity == SEV_WARNING:
        return "warning"
    if severity == SEV_UNKNOWN:
        return "unknown"
    return "healthy"


def _severity_worse(current: int, incoming: int) -> int:
    if current == SEV_UNKNOWN:
        return incoming
    if incoming == SEV_UNKNOWN:
        return current
    return max(current, incoming)


def _cache_key_for_host(host_header: str) -> str:
    normalized = (host_header or "").strip().lower()
    return normalized if normalized else "__no_host__"


def _parse_host_to_public_base(host_header: str) -> Optional[str]:
    configured = (settings.monitor_public_base_url or "").strip()
    if configured:
        configured_url = configured if "://" in configured else f"https://{configured}"
        parsed = urlparse(configured_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logger.warning("Ignoring invalid MONITOR_PUBLIC_BASE_URL: %s", configured)
            return None
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

    host = (host_header or "").strip().lower()
    if not host:
        return None

    if not _SAFE_HOST_RE.fullmatch(host):
        logger.warning("Ignoring unsafe Host header for ops summary probe: %s", host_header)
        return None

    host_name = host.rsplit(":", 1)[0]
    host_name_clean = host_name[1:-1] if host_name.startswith("[") and host_name.endswith("]") else host_name
    configured_host = settings.domain.split("://")[-1].split("/", 1)[0].lower()
    configured_host_name = configured_host.rsplit(":", 1)[0]
    trusted_hosts = {
        "localhost",
        "127.0.0.1",
        "::1",
        "[::1]",
        configured_host,
        configured_host_name,
    }
    for origin in settings.cors_origins_list:
        origin_url = origin if "://" in origin else f"http://{origin}"
        parsed_origin = urlparse(origin_url)
        netloc = (parsed_origin.netloc or "").lower()
        if netloc:
            trusted_hosts.add(netloc)
            trusted_hosts.add(netloc.rsplit(":", 1)[0])

    trusted_by_exact = (
        host in trusted_hosts
        or host_name in trusted_hosts
        or host_name_clean in trusted_hosts
    )
    trusted_by_suffix = (
        bool(configured_host_name)
        and "." in configured_host_name
        and (
            host_name_clean == configured_host_name
            or host_name_clean.endswith(f".{configured_host_name}")
        )
    )

    if not trusted_by_exact and not trusted_by_suffix:
        logger.warning("Ignoring untrusted Host header for ops summary probe: %s", host_header)
        return None

    prefer_https = "." in host_name_clean and host_name_clean not in {"localhost", "127.0.0.1", "::1"}
    scheme = "https" if prefer_https else "http"
    return f"{scheme}://{host}".rstrip("/")


async def _probe_url(url: Optional[str], timeout_sec: float) -> Dict[str, Any]:
    if not url:
        return {
            "url": None,
            "ok": False,
            "status_code": None,
            "latency_ms": None,
            "error": "probe_url_missing",
            "headers": {},
        }

    started = time.perf_counter()
    headers = {"User-Agent": "ops-summary-probe/1.0", "Accept": "application/json,text/plain,*/*"}
    try:
        async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
        latency_ms = (time.perf_counter() - started) * 1000.0
        safe_headers = {
            "server": response.headers.get("server"),
            "cf_ray": response.headers.get("cf-ray"),
            "cf_cache_status": response.headers.get("cf-cache-status"),
            "content_type": response.headers.get("content-type"),
        }
        return {
            "url": url,
            "ok": 200 <= response.status_code < 400,
            "status_code": int(response.status_code),
            "latency_ms": round(latency_ms, 2),
            "error": None,
            "headers": safe_headers,
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000.0
        return {
            "url": url,
            "ok": False,
            "status_code": None,
            "latency_ms": round(latency_ms, 2),
            "error": str(exc),
            "headers": {},
        }


def _evaluate_cloudflare_layer(
    edge_probe: Dict[str, Any],
    *,
    expect_cloudflare_proxy: bool,
) -> Tuple[int, Dict[str, Any], str]:
    code = edge_probe.get("status_code")
    error = edge_probe.get("error")
    cf_ray = (edge_probe.get("headers") or {}).get("cf_ray")

    if edge_probe.get("url") is None:
        return SEV_UNKNOWN, {}, "Public URL belum dikonfigurasi"

    if error:
        return SEV_CRITICAL, {"error": error}, "Edge tidak merespons"
    if code is None:
        return SEV_CRITICAL, {}, "Edge probe gagal"
    if code >= 500:
        return SEV_CRITICAL, {"status_code": code}, "Edge mengembalikan 5xx"
    if code >= 400:
        return SEV_WARNING, {"status_code": code}, "Edge mengembalikan 4xx"
    if not cf_ray:
        if expect_cloudflare_proxy:
            return (
                SEV_WARNING,
                {
                    "status_code": code,
                    "proxy_expected": True,
                    "proxy_detected": False,
                    "proxy_mode": "expected_but_not_detected",
                },
                "Respon sehat tetapi header Cloudflare tidak terdeteksi",
            )
        return (
            SEV_HEALTHY,
            {
                "status_code": code,
                "proxy_expected": False,
                "proxy_detected": False,
                "proxy_mode": "dns_only",
            },
            "DNS-only aktif (tanpa proxy Cloudflare), origin publik sehat",
        )

    return (
        SEV_HEALTHY,
        {
            "status_code": code,
            "cf_ray_present": True,
            "proxy_expected": bool(expect_cloudflare_proxy),
            "proxy_detected": True,
            "proxy_mode": "proxied",
        },
        "Edge sehat",
    )


def _evaluate_frontend_layer(static_probe: Dict[str, Any]) -> Tuple[int, Dict[str, Any], str]:
    code = static_probe.get("status_code")
    error = static_probe.get("error")
    if error:
        return SEV_CRITICAL, {"error": error}, "Asset frontend gagal diambil"
    if code is None:
        return SEV_CRITICAL, {}, "Probe frontend gagal"
    if code >= 500:
        return SEV_CRITICAL, {"status_code": code}, "Frontend static mengembalikan 5xx"
    if code >= 400:
        return SEV_WARNING, {"status_code": code}, "Frontend static mengembalikan 4xx"
    return SEV_HEALTHY, {"status_code": code}, "Frontend static sehat"


def _count_runtime_requests(runtime: Dict[str, Any]) -> Tuple[int, int]:
    global_requests = int((runtime.get("global") or {}).get("requests") or 0)
    critical_endpoints = runtime.get("critical_endpoints") or {}
    critical_request_count = sum(
        int((critical_endpoints.get(key) or {}).get("requests") or 0)
        for key in ("auth_signin", "exam_start", "submit_answer", "exam_submit")
    )
    return global_requests, critical_request_count


def _evaluate_backend_layer(
    runtime: Dict[str, Any],
    origin_probe: Dict[str, Any],
    *,
    active_sessions: int = 0,
) -> Tuple[int, Dict[str, Any], str]:
    severity = SEV_HEALTHY
    reasons: List[str] = []

    global_5xx = float(runtime.get("global", {}).get("error_rate_percent", 0.0) or 0.0)
    critical_endpoints = runtime.get("critical_endpoints", {}) or {}
    global_requests, critical_request_count = _count_runtime_requests(runtime)
    p95_values = [
        float((critical_endpoints.get(key) or {}).get("p95_latency_ms", 0.0) or 0.0)
        for key in ("auth_signin", "exam_start", "submit_answer")
    ]
    max_p95 = max(p95_values) if p95_values else 0.0

    if global_5xx > 3.0:
        severity = _severity_worse(severity, SEV_CRITICAL)
        reasons.append(f"5xx {global_5xx:.2f}%")
    elif global_5xx > 1.0:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"5xx {global_5xx:.2f}%")

    if max_p95 > 3500:
        severity = _severity_worse(severity, SEV_CRITICAL)
        reasons.append(f"p95 {max_p95:.0f}ms")
    elif max_p95 > 2000:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"p95 {max_p95:.0f}ms")

    if origin_probe.get("error"):
        severity = _severity_worse(severity, SEV_CRITICAL)
        reasons.append("origin probe gagal")
    elif (origin_probe.get("status_code") or 0) >= 500:
        severity = _severity_worse(severity, SEV_CRITICAL)
        reasons.append(f"origin {origin_probe.get('status_code')}")

    if active_sessions > 0 and global_requests <= 0:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"telemetry kosong saat {active_sessions} sesi aktif")

    if reasons:
        summary = f"Perlu perhatian: {', '.join(reasons)}"
    elif global_requests <= 0:
        summary = "Backend sehat via health probe, trafik runtime 60 detik sedang idle"
    elif critical_request_count <= 0:
        summary = "Backend sehat, tetapi endpoint kritikal belum punya sampel baru"
    else:
        summary = "Backend sehat"

    metrics = {
        "global_5xx_percent": round(global_5xx, 3),
        "max_critical_p95_ms": round(max_p95, 2),
        "origin_status_code": origin_probe.get("status_code"),
        "origin_latency_ms": origin_probe.get("latency_ms"),
        "global_request_count_60s": global_requests,
        "critical_request_count_180s": critical_request_count,
        "active_sessions": active_sessions,
    }
    return severity, metrics, summary


def _evaluate_db_layer(metrics: Dict[str, Any], runtime: Dict[str, Any]) -> Tuple[int, Dict[str, Any], str]:
    severity = SEV_HEALTHY
    reasons: List[str] = []

    conn_percent = float(((metrics.get("connections") or {}).get("percent_used") or 0.0))
    slow_queries = int(((metrics.get("performance") or {}).get("slow_queries") or 0))
    db_pool_timeout = float(((runtime.get("event_rates_per_min") or {}).get("db_pool_timeout") or 0.0))

    if conn_percent > 95:
        severity = SEV_CRITICAL
        reasons.append(f"DB conn {conn_percent:.1f}%")
    elif conn_percent > 85:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"DB conn {conn_percent:.1f}%")

    if db_pool_timeout > 1.0:
        severity = _severity_worse(severity, SEV_CRITICAL)
        reasons.append(f"pool timeout {db_pool_timeout:.2f}/min")

    if slow_queries > 100:
        severity = _severity_worse(severity, SEV_CRITICAL)
        reasons.append(f"slow query {slow_queries}")
    elif slow_queries > 30:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"slow query {slow_queries}")

    summary = "Database sehat" if not reasons else f"Perlu perhatian: {', '.join(reasons)}"
    return severity, {
        "connection_percent_used": round(conn_percent, 2),
        "slow_queries": slow_queries,
        "db_pool_timeout_per_min": round(db_pool_timeout, 2),
    }, summary


def _evaluate_redis_layer(metrics: Dict[str, Any], runtime: Dict[str, Any]) -> Tuple[int, Dict[str, Any], str]:
    severity = SEV_HEALTHY
    reasons: List[str] = []
    advisories: List[str] = []

    blocked_warning = int(getattr(settings, "redis_blocked_clients_warning", 10))
    blocked_critical = int(getattr(settings, "redis_blocked_clients_critical", 30))
    timeout_warning = float(getattr(settings, "redis_timeout_warning_per_min", 0.2))
    timeout_critical = float(getattr(settings, "redis_timeout_critical_per_min", 1.0))
    cache_hit_warning = float(getattr(settings, "redis_cache_hit_warning_percent", 35.0))
    cache_hit_critical = float(getattr(settings, "redis_cache_hit_critical_percent", 20.0))
    cache_hit_min_lookups = int(getattr(settings, "redis_cache_hit_min_lookups", 3000))
    cache_hit_hard_critical_min_lookups = int(
        getattr(settings, "redis_cache_hit_hard_critical_min_lookups", 15000)
    )
    cache_hit_penalty_requires_pressure = bool(
        getattr(settings, "redis_cache_hit_penalty_requires_pressure", True)
    )
    cache_hit_penalty_high_volume_min_lookups = int(
        getattr(settings, "redis_cache_hit_penalty_high_volume_min_lookups", 50000)
    )
    memory_warning = float(getattr(settings, "redis_memory_warning_percent", 85.0))
    memory_critical = float(getattr(settings, "redis_memory_critical_percent", 95.0))
    stability_target = float(getattr(settings, "redis_stability_target_percent", 100.0))

    blocked_clients = int(((metrics.get("clients") or {}).get("blocked_clients") or 0))
    redis_timeout = float(((runtime.get("event_rates_per_min") or {}).get("redis_timeout") or 0.0))
    stats = metrics.get("stats") or {}
    memory = metrics.get("memory") or {}

    keyspace_hits = int((stats or {}).get("keyspace_hits") or 0)
    keyspace_misses = int((stats or {}).get("keyspace_misses") or 0)
    cache_hit_lifetime = float((stats or {}).get("cache_hit_ratio") or 0.0)

    cache_lookup_delta = int((stats or {}).get("cache_lookup_delta") or 0)
    cache_window_seconds = float((stats or {}).get("window_seconds") or 0.0)
    cache_hit_window_raw = (stats or {}).get("cache_hit_ratio_window")
    cache_hit_window = float(cache_hit_window_raw) if cache_hit_window_raw is not None else None

    if cache_hit_window is not None:
        cache_hit = cache_hit_window
        cache_lookup_total = max(0, cache_lookup_delta)
        cache_source = "window"
    else:
        cache_hit = cache_hit_lifetime
        cache_lookup_total = max(0, keyspace_hits + keyspace_misses)
        cache_source = "lifetime"

    maxmemory = int((memory or {}).get("maxmemory") or 0)
    memory_percent = float((memory or {}).get("percent_used_of_maxmemory") or 0.0)
    eval_cache = cache_lookup_total >= cache_hit_min_lookups
    pressure_signal = False
    high_volume_signal = cache_lookup_total >= cache_hit_penalty_high_volume_min_lookups
    cache_penalty_allowed = (not cache_hit_penalty_requires_pressure) or high_volume_signal
    cache_penalty_applied = False

    if blocked_clients >= blocked_critical:
        severity = SEV_CRITICAL
        reasons.append(f"blocked {blocked_clients}")
        pressure_signal = True
    elif blocked_clients >= blocked_warning:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"blocked {blocked_clients}")
        pressure_signal = True

    if redis_timeout >= timeout_critical:
        severity = _severity_worse(severity, SEV_CRITICAL)
        reasons.append(f"timeout {redis_timeout:.2f}/min")
        pressure_signal = True
    elif redis_timeout >= timeout_warning:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"timeout {redis_timeout:.2f}/min")
        pressure_signal = True

    if maxmemory > 0:
        if memory_percent >= memory_critical:
            severity = _severity_worse(severity, SEV_CRITICAL)
            reasons.append(f"memory {memory_percent:.1f}%")
            pressure_signal = True
        elif memory_percent >= memory_warning:
            severity = _severity_worse(severity, SEV_WARNING)
            reasons.append(f"memory {memory_percent:.1f}%")
            pressure_signal = True

    # Cache-hit ratio is advisory unless traffic volume is high enough.
    if eval_cache and cache_hit < cache_hit_warning:
        cache_message = f"cache hit {cache_hit:.1f}% ({cache_source})"
        if cache_hit_penalty_requires_pressure:
            cache_penalty_allowed = pressure_signal or high_volume_signal
        if cache_penalty_allowed:
            severity = _severity_worse(severity, SEV_WARNING)
            reasons.append(cache_message)
            cache_penalty_applied = True
            if (
                cache_hit < cache_hit_critical
                and cache_lookup_total >= cache_hit_hard_critical_min_lookups
                and pressure_signal
            ):
                severity = _severity_worse(severity, SEV_CRITICAL)
        else:
            advisories.append(cache_message)

    stability_score = 100.0
    if blocked_clients >= blocked_warning:
        stability_score -= min(30.0, blocked_clients * 1.8)
    if redis_timeout >= timeout_warning:
        stability_score -= min(45.0, redis_timeout * 35.0)
    if maxmemory > 0 and memory_percent > 70.0:
        stability_score -= min(20.0, (memory_percent - 70.0) * 0.6)
    if eval_cache:
        if cache_hit < stability_target and cache_penalty_allowed:
            stability_score -= min(25.0, (stability_target - cache_hit) * 0.25)
    stability_score = round(_clamp(stability_score, 0.0, 100.0), 2)

    if reasons:
        summary = f"Perlu perhatian: {', '.join(reasons)}"
    elif advisories:
        summary = f"Redis sehat (stability {stability_score:.1f}%, advisory: {', '.join(advisories)})"
    else:
        summary = f"Redis sehat (stability {stability_score:.1f}%)"
    return severity, {
        "redis_stability_score_percent": stability_score,
        "blocked_clients": blocked_clients,
        "redis_timeout_per_min": round(redis_timeout, 2),
        "cache_hit_ratio_percent": round(cache_hit, 2),
        "cache_hit_ratio_lifetime_percent": round(cache_hit_lifetime, 2),
        "cache_lookup_total": cache_lookup_total,
        "cache_eval_enabled": bool(eval_cache),
        "cache_ratio_source": cache_source,
        "cache_lookup_window_seconds": round(cache_window_seconds, 2),
        "cache_penalty_allowed": bool(cache_penalty_allowed),
        "cache_penalty_applied": bool(cache_penalty_applied),
        "cache_pressure_signal": bool(pressure_signal),
        "cache_high_volume_signal": bool(high_volume_signal),
        "memory_percent_used_of_maxmemory": round(memory_percent, 2),
        "maxmemory_bytes": maxmemory,
        "instantaneous_ops_per_sec": int((stats or {}).get("instantaneous_ops_per_sec") or 0),
    }, summary


def _evaluate_host_layer(metrics: Dict[str, Any]) -> Tuple[int, Dict[str, Any], str]:
    severity = SEV_HEALTHY
    reasons: List[str] = []

    cpu_percent = float(((metrics.get("cpu") or {}).get("percent") or 0.0))
    memory_percent = float(((metrics.get("memory") or {}).get("percent") or 0.0))
    disk_percent = float(((metrics.get("disk") or {}).get("percent") or 0.0))

    if cpu_percent > 95:
        severity = SEV_CRITICAL
        reasons.append(f"CPU {cpu_percent:.1f}%")
    elif cpu_percent > 85:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"CPU {cpu_percent:.1f}%")

    if memory_percent > 92:
        severity = _severity_worse(severity, SEV_CRITICAL)
        reasons.append(f"RAM {memory_percent:.1f}%")
    elif memory_percent > 85:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"RAM {memory_percent:.1f}%")

    if disk_percent > 95:
        severity = _severity_worse(severity, SEV_CRITICAL)
        reasons.append(f"Disk {disk_percent:.1f}%")
    elif disk_percent > 90:
        severity = _severity_worse(severity, SEV_WARNING)
        reasons.append(f"Disk {disk_percent:.1f}%")

    summary = "Host sehat" if not reasons else f"Perlu perhatian: {', '.join(reasons)}"
    return severity, {
        "cpu_percent": round(cpu_percent, 2),
        "memory_percent": round(memory_percent, 2),
        "disk_percent": round(disk_percent, 2),
    }, summary


def _build_root_cause_hints(
    layer_status: Dict[str, int],
    runtime: Dict[str, Any],
    application_metrics: Optional[Dict[str, Any]] = None,
    auto_restart_schedule: Optional[Dict[str, Any]] = None,
    auto_restart_status: Optional[Dict[str, Any]] = None,
) -> List[str]:
    hints: List[str] = []

    if layer_status.get("cloudflare_edge") == SEV_CRITICAL and layer_status.get("backend_api", SEV_UNKNOWN) <= SEV_WARNING:
        hints.append("Kemungkinan isu dominan di jalur edge/Cloudflare (origin relatif sehat).")

    if layer_status.get("backend_api") == SEV_CRITICAL and layer_status.get("database") == SEV_CRITICAL:
        hints.append("Bottleneck backend dipengaruhi tekanan database (connection/pool timeout).")

    if layer_status.get("redis") == SEV_CRITICAL:
        hints.append("Redis mengalami tekanan tinggi, cek timeout, blocked clients, dan memory.")

    if layer_status.get("host") == SEV_CRITICAL:
        hints.append("Sumber daya VPS kritikal, prioritaskan stabilisasi CPU/RAM/disk.")

    global_5xx = float((runtime.get("global") or {}).get("error_rate_percent") or 0.0)
    if global_5xx > 3.0:
        hints.append("5xx sudah melewati ambang kritikal, naikkan mode resource ke HIGH/EXTREME sementara.")

    active_sessions = int(((application_metrics or {}).get("sessions") or {}).get("active") or 0)
    global_requests, critical_request_count = _count_runtime_requests(runtime)
    if active_sessions > 0 and global_requests <= 0:
        hints.append(
            f"Ada {active_sessions} sesi aktif, tetapi telemetry request 60 detik kosong. "
            "Cek jalur request API atau middleware telemetry."
        )
    elif global_requests <= 0:
        hints.append("Trafik runtime 60 detik sedang idle; status backend terutama berdasarkan probe /health.")
    elif critical_request_count <= 0:
        hints.append(
            "Belum ada sampel endpoint kritikal pada window telemetry terbaru; "
            "p95 login/mulai/kumpulkan ujian belum representatif."
        )

    restart_enabled = bool((auto_restart_schedule or {}).get("enabled", False))
    restart_state = str((auto_restart_status or {}).get("state") or "").lower()
    restart_pending = int((auto_restart_status or {}).get("pending_count") or 0)
    restart_next_wib = str((auto_restart_status or {}).get("next_run_at_wib") or "").strip()
    if not restart_enabled:
        hints.append("Auto restart terjadwal OFF. Aktifkan agar maintenance antar sesi berjalan konsisten.")
    elif restart_state in {"failed", "blocked"}:
        hints.append("Auto restart terjadwal gagal/terblokir di run terakhir. Cek guard ujian aktif dan log monitoring.")
    elif restart_pending <= 0:
        hints.append("Auto restart aktif, tetapi belum ada jadwal pending. Tambahkan jadwal WIB dari dashboard.")
    else:
        hints.append(
            f"Auto restart aktif dengan {restart_pending} jadwal pending."
            + (f" Next: {restart_next_wib}." if restart_next_wib else "")
        )

    if not hints:
        hints.append("Tidak ada indikator kritikal; lanjutkan monitoring berkala.")
    return hints


async def get_ops_summary(host_header: str, db: AsyncSession) -> Dict[str, Any]:
    """Return cached selective ops summary for admin monitoring dashboard."""
    global _cache_payload_by_host, _cache_at_monotonic_by_host

    cache_ttl = int(_clamp(float(settings.monitor_probe_cache_seconds), 5, 60))
    now_mono = time.monotonic()
    cache_key = _cache_key_for_host(host_header)

    async with _cache_lock:
        cached_payload = _cache_payload_by_host.get(cache_key)
        cached_at = float(_cache_at_monotonic_by_host.get(cache_key, 0.0))
        if cached_payload and (now_mono - cached_at) < cache_ttl:
            return cached_payload

        await metrics_collector.initialize()
        all_metrics = await metrics_collector.collect_all_metrics(db)
        runtime_snapshot = await get_runtime_snapshot(window_seconds=60, latency_window_seconds=180)
        policy = await get_runtime_policy(force_refresh=True)
        auto_restart_schedule = await get_auto_restart_schedule(force_refresh=True)
        auto_restart_status = await get_auto_restart_status(force_refresh=True)

        public_base = _parse_host_to_public_base(host_header)
        edge_url = f"{public_base}/health" if public_base else None
        static_url = f"{public_base}/static/js/api.js?v=ops-probe" if public_base else None
        origin_url = (settings.monitor_origin_health_url or "http://127.0.0.1:8000/health").strip()
        timeout_sec = _clamp(settings.monitor_probe_timeout_ms / 1000.0, 0.8, 8.0)

        edge_probe, static_probe, origin_probe = await asyncio.gather(
            _probe_url(edge_url, timeout_sec=timeout_sec),
            _probe_url(static_url, timeout_sec=timeout_sec),
            _probe_url(origin_url, timeout_sec=timeout_sec),
        )

        system_metrics = all_metrics.get("system", {}) or {}
        db_metrics = all_metrics.get("database", {}) or {}
        redis_metrics = all_metrics.get("redis", {}) or {}
        application_metrics = all_metrics.get("application", {}) or {}

        cloudflare_proxy_expected = bool(settings.monitor_expect_cloudflare_proxy)
        cloudflare_sev, cloudflare_data, cloudflare_summary = _evaluate_cloudflare_layer(
            edge_probe,
            expect_cloudflare_proxy=cloudflare_proxy_expected,
        )
        frontend_sev, frontend_data, frontend_summary = _evaluate_frontend_layer(static_probe)
        backend_sev, backend_data, backend_summary = _evaluate_backend_layer(
            runtime_snapshot,
            origin_probe,
            active_sessions=int((application_metrics.get("sessions") or {}).get("active") or 0),
        )
        db_sev, db_data, db_summary = _evaluate_db_layer(db_metrics, runtime_snapshot)
        redis_sev, redis_data, redis_summary = _evaluate_redis_layer(redis_metrics, runtime_snapshot)
        host_sev, host_data, host_summary = _evaluate_host_layer(system_metrics)

        layer_status = {
            "cloudflare_edge": cloudflare_sev,
            "frontend_static": frontend_sev,
            "backend_api": backend_sev,
            "database": db_sev,
            "redis": redis_sev,
            "host": host_sev,
        }

        overall_sev = SEV_HEALTHY
        for sev in layer_status.values():
            overall_sev = _severity_worse(overall_sev, sev)

        critical_endpoints = (runtime_snapshot.get("critical_endpoints") or {})
        key_metrics = {
            "global_5xx_percent": round(float((runtime_snapshot.get("global") or {}).get("error_rate_percent") or 0.0), 3),
            "auth_signin_p95_ms": round(float((critical_endpoints.get("auth_signin") or {}).get("p95_latency_ms") or 0.0), 2),
            "exam_start_p95_ms": round(float((critical_endpoints.get("exam_start") or {}).get("p95_latency_ms") or 0.0), 2),
            "submit_answer_p95_ms": round(float((critical_endpoints.get("submit_answer") or {}).get("p95_latency_ms") or 0.0), 2),
            "db_connection_percent": round(float((db_metrics.get("connections") or {}).get("percent_used") or 0.0), 2),
            "redis_blocked_clients": int((redis_metrics.get("clients") or {}).get("blocked_clients") or 0),
            "redis_stability_score_percent": round(float(redis_data.get("redis_stability_score_percent", 0.0) or 0.0), 2),
            "cpu_percent": round(float((system_metrics.get("cpu") or {}).get("percent") or 0.0), 2),
            "memory_percent": round(float((system_metrics.get("memory") or {}).get("percent") or 0.0), 2),
        }

        payload: Dict[str, Any] = {
            "status": _status_from_severity(overall_sev),
            "updated_at": _now_iso(),
            "degrade_mode": bool(policy.get("degrade_mode", False)),
            "policy": {
                "degrade_mode": bool(policy.get("degrade_mode", False)),
                "resource_mode": policy.get("resource_mode", "normal"),
                "resource_mode_label": policy.get("resource_mode_label"),
                "resource_mode_description": policy.get("resource_mode_description"),
                "delayed_features": policy.get("delayed_features", []),
                "reason": policy.get("reason"),
                "expires_at": policy.get("expires_at"),
                "auto_restart_enabled": bool(auto_restart_schedule.get("enabled", False)),
                "auto_restart_time_wib": auto_restart_schedule.get("time_wib"),
                "auto_restart_timezone": auto_restart_schedule.get("timezone", "Asia/Jakarta"),
                "auto_restart_pending_count": int(auto_restart_status.get("pending_count") or 0),
                "auto_restart_next_run_wib": auto_restart_status.get("next_run_at_wib"),
                "auto_restart_state": auto_restart_status.get("state"),
                "auto_restart_updated_at": auto_restart_schedule.get("updated_at"),
                "cloudflare_proxy_expected": cloudflare_proxy_expected,
            },
            "auto_restart": {
                "enabled": bool(auto_restart_schedule.get("enabled", False)),
                "timezone": auto_restart_schedule.get("timezone", "Asia/Jakarta"),
                "time_wib": auto_restart_schedule.get("time_wib"),
                "restart_buffer_minutes": auto_restart_schedule.get("restart_buffer_minutes"),
                "full_restart": bool(auto_restart_schedule.get("full_restart", True)),
                "include_data_services": bool(auto_restart_schedule.get("include_data_services", True)),
                "restart_timeout_seconds": auto_restart_schedule.get("restart_timeout_seconds"),
                "reason": auto_restart_schedule.get("reason"),
                "source": auto_restart_schedule.get("source"),
                "actor": auto_restart_schedule.get("actor"),
                "updated_at": auto_restart_schedule.get("updated_at"),
                "entries": (auto_restart_schedule.get("entries") or [])[:20],
                "status": auto_restart_status,
            },
            "key_metrics": key_metrics,
            "activity": {
                "active_sessions": int((application_metrics.get("sessions") or {}).get("active") or 0),
                "published_exams": int((application_metrics.get("exams") or {}).get("published") or 0),
            },
            "layers": [
                {
                    "id": "cloudflare_edge",
                    "label": (
                        "Cloudflare Edge"
                        if cloudflare_proxy_expected
                        else "Public Edge (DNS-only)"
                    ),
                    "status": _status_from_severity(cloudflare_sev),
                    "summary": cloudflare_summary,
                    "metrics": {
                        **cloudflare_data,
                        "latency_ms": edge_probe.get("latency_ms"),
                        "cf_ray": (edge_probe.get("headers") or {}).get("cf_ray"),
                    },
                },
                {
                    "id": "frontend_static",
                    "label": "Frontend Static",
                    "status": _status_from_severity(frontend_sev),
                    "summary": frontend_summary,
                    "metrics": {
                        **frontend_data,
                        "latency_ms": static_probe.get("latency_ms"),
                    },
                },
                {
                    "id": "backend_api",
                    "label": "Backend API",
                    "status": _status_from_severity(backend_sev),
                    "summary": backend_summary,
                    "metrics": backend_data,
                },
                {
                    "id": "database",
                    "label": "PostgreSQL",
                    "status": _status_from_severity(db_sev),
                    "summary": db_summary,
                    "metrics": db_data,
                },
                {
                    "id": "redis",
                    "label": "Redis",
                    "status": _status_from_severity(redis_sev),
                    "summary": redis_summary,
                    "metrics": redis_data,
                },
                {
                    "id": "host",
                    "label": "VPS Host",
                    "status": _status_from_severity(host_sev),
                    "summary": host_summary,
                    "metrics": host_data,
                },
            ],
            "thresholds": {
                "http_5xx_warning_percent": 1.0,
                "http_5xx_critical_percent": 3.0,
                "p95_warning_ms": 2000,
                "db_connection_warning_percent": 85,
                "db_connection_critical_percent": 95,
                "redis_blocked_clients_warning": int(getattr(settings, "redis_blocked_clients_warning", 10)),
                "redis_blocked_clients_critical": int(getattr(settings, "redis_blocked_clients_critical", 30)),
                "redis_timeout_warning_per_min": float(getattr(settings, "redis_timeout_warning_per_min", 0.2)),
                "redis_timeout_critical_per_min": float(getattr(settings, "redis_timeout_critical_per_min", 1.0)),
                "redis_cache_hit_warning_percent": float(getattr(settings, "redis_cache_hit_warning_percent", 35.0)),
                "redis_cache_hit_critical_percent": float(getattr(settings, "redis_cache_hit_critical_percent", 20.0)),
                "redis_cache_hit_min_lookups": int(getattr(settings, "redis_cache_hit_min_lookups", 3000)),
                "redis_cache_hit_hard_critical_min_lookups": int(
                    getattr(settings, "redis_cache_hit_hard_critical_min_lookups", 15000)
                ),
                "redis_cache_hit_penalty_requires_pressure": bool(
                    getattr(settings, "redis_cache_hit_penalty_requires_pressure", True)
                ),
                "redis_cache_hit_penalty_high_volume_min_lookups": int(
                    getattr(settings, "redis_cache_hit_penalty_high_volume_min_lookups", 50000)
                ),
                "redis_memory_warning_percent": float(getattr(settings, "redis_memory_warning_percent", 85.0)),
                "redis_memory_critical_percent": float(getattr(settings, "redis_memory_critical_percent", 95.0)),
                "redis_stability_target_percent": float(getattr(settings, "redis_stability_target_percent", 100.0)),
                "cpu_warning_percent": 85,
                "cpu_critical_percent": 95,
            },
            "hints": _build_root_cause_hints(
                layer_status=layer_status,
                runtime=runtime_snapshot,
                application_metrics=application_metrics,
                auto_restart_schedule=auto_restart_schedule,
                auto_restart_status=auto_restart_status,
            ),
        }

        _cache_payload_by_host[cache_key] = payload
        _cache_at_monotonic_by_host[cache_key] = now_mono
        return payload


def invalidate_ops_summary_cache() -> None:
    """Invalidate in-process ops summary cache (call after manual state toggles)."""
    global _cache_payload_by_host, _cache_at_monotonic_by_host
    _cache_payload_by_host = {}
    _cache_at_monotonic_by_host = {}
