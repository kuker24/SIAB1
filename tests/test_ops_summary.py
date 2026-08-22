from app.core.ops_summary import (
    SEV_CRITICAL,
    SEV_HEALTHY,
    SEV_WARNING,
    _build_root_cause_hints,
    _evaluate_backend_layer,
    _evaluate_cloudflare_layer,
    _evaluate_redis_layer,
)


def _runtime_payload(
    *,
    global_requests: int,
    global_5xx_percent: float = 0.0,
    auth_requests: int = 0,
    exam_start_requests: int = 0,
    submit_answer_requests: int = 0,
    exam_submit_requests: int = 0,
    auth_p95_ms: float = 0.0,
    exam_start_p95_ms: float = 0.0,
    submit_answer_p95_ms: float = 0.0,
) -> dict:
    return {
        "global": {
            "requests": global_requests,
            "errors_5xx": 0,
            "error_rate_percent": global_5xx_percent,
        },
        "critical_endpoints": {
            "auth_signin": {
                "requests": auth_requests,
                "errors_5xx": 0,
                "error_rate_percent": 0.0,
                "p95_latency_ms": auth_p95_ms,
            },
            "exam_start": {
                "requests": exam_start_requests,
                "errors_5xx": 0,
                "error_rate_percent": 0.0,
                "p95_latency_ms": exam_start_p95_ms,
            },
            "submit_answer": {
                "requests": submit_answer_requests,
                "errors_5xx": 0,
                "error_rate_percent": 0.0,
                "p95_latency_ms": submit_answer_p95_ms,
            },
            "exam_submit": {
                "requests": exam_submit_requests,
                "errors_5xx": 0,
                "error_rate_percent": 0.0,
                "p95_latency_ms": 0.0,
            },
        },
        "event_rates_per_min": {
            "db_pool_timeout": 0.0,
            "redis_timeout": 0.0,
        },
    }


def _origin_probe(status_code: int = 200, latency_ms: float = 35.0) -> dict:
    return {
        "status_code": status_code,
        "latency_ms": latency_ms,
        "error": None,
    }


def test_backend_layer_idle_runtime_mentions_health_probe() -> None:
    severity, metrics, summary = _evaluate_backend_layer(
        _runtime_payload(global_requests=0),
        _origin_probe(),
        active_sessions=0,
    )

    assert severity == SEV_HEALTHY
    assert metrics["global_request_count_60s"] == 0
    assert metrics["critical_request_count_180s"] == 0
    assert "health probe" in summary
    assert "idle" in summary


def test_backend_layer_warns_when_active_sessions_have_no_runtime_traffic() -> None:
    severity, metrics, summary = _evaluate_backend_layer(
        _runtime_payload(global_requests=0),
        _origin_probe(),
        active_sessions=14,
    )

    assert severity == SEV_WARNING
    assert metrics["active_sessions"] == 14
    assert "telemetry kosong" in summary


def test_backend_layer_keeps_healthy_when_runtime_clean_but_no_critical_samples() -> None:
    severity, metrics, summary = _evaluate_backend_layer(
        _runtime_payload(global_requests=9),
        _origin_probe(),
        active_sessions=0,
    )

    assert severity == SEV_HEALTHY
    assert metrics["global_request_count_60s"] == 9
    assert metrics["critical_request_count_180s"] == 0
    assert "endpoint kritikal belum punya sampel baru" in summary


def test_backend_layer_stays_critical_for_real_5xx_incident() -> None:
    severity, metrics, summary = _evaluate_backend_layer(
        _runtime_payload(
            global_requests=42,
            global_5xx_percent=4.2,
            submit_answer_requests=18,
            submit_answer_p95_ms=850.0,
        ),
        _origin_probe(),
        active_sessions=31,
    )

    assert severity == SEV_CRITICAL
    assert metrics["global_5xx_percent"] == 4.2
    assert "5xx 4.20%" in summary


def test_root_cause_hints_calls_out_idle_runtime_window() -> None:
    hints = _build_root_cause_hints(
        layer_status={
            "cloudflare_edge": SEV_HEALTHY,
            "backend_api": SEV_HEALTHY,
            "database": SEV_HEALTHY,
            "redis": SEV_HEALTHY,
            "host": SEV_HEALTHY,
        },
        runtime=_runtime_payload(global_requests=0),
        application_metrics={"sessions": {"active": 0}},
        auto_restart_schedule={"enabled": False},
        auto_restart_status={},
    )

    assert any("idle" in hint for hint in hints)


def _redis_metrics_payload(
    *,
    blocked_clients: int = 0,
    cache_hit_window: float = 15.0,
    cache_lookup_delta: int = 20000,
    memory_percent: float = 20.0,
) -> dict:
    return {
        "clients": {
            "blocked_clients": blocked_clients,
        },
        "stats": {
            "keyspace_hits": 100000,
            "keyspace_misses": 200000,
            "cache_hit_ratio": 33.3,
            "cache_lookup_delta": cache_lookup_delta,
            "cache_hit_ratio_window": cache_hit_window,
            "window_seconds": 60.0,
            "instantaneous_ops_per_sec": 8,
        },
        "memory": {
            "maxmemory": 1_000_000_000,
            "percent_used_of_maxmemory": memory_percent,
        },
    }


def _runtime_events_payload(*, redis_timeout_per_min: float = 0.0) -> dict:
    return {
        "event_rates_per_min": {
            "redis_timeout": redis_timeout_per_min,
        }
    }


def test_redis_low_cache_hit_without_pressure_stays_healthy() -> None:
    severity, metrics, summary = _evaluate_redis_layer(
        _redis_metrics_payload(cache_hit_window=18.0, cache_lookup_delta=21000),
        _runtime_events_payload(redis_timeout_per_min=0.0),
    )

    assert severity == SEV_HEALTHY
    assert metrics["cache_penalty_applied"] is False
    assert metrics["cache_penalty_allowed"] is False
    assert metrics["redis_stability_score_percent"] >= 99.0
    assert "advisory" in summary


def test_redis_low_cache_hit_with_runtime_pressure_triggers_penalty() -> None:
    severity, metrics, summary = _evaluate_redis_layer(
        _redis_metrics_payload(cache_hit_window=22.0, cache_lookup_delta=22000),
        _runtime_events_payload(redis_timeout_per_min=0.8),
    )

    assert severity == SEV_WARNING
    assert metrics["cache_penalty_applied"] is True
    assert metrics["cache_penalty_allowed"] is True
    assert metrics["redis_stability_score_percent"] < 95.0
    assert "cache hit" in summary


def test_cloudflare_layer_dns_only_without_cf_ray_stays_healthy() -> None:
    severity, metrics, summary = _evaluate_cloudflare_layer(
        {"url": "https://example.test/health", "status_code": 200, "error": None, "headers": {}},
        expect_cloudflare_proxy=False,
    )

    assert severity == SEV_HEALTHY
    assert metrics["proxy_mode"] == "dns_only"
    assert metrics["proxy_detected"] is False
    assert "DNS-only" in summary


def test_cloudflare_layer_expected_proxy_without_cf_ray_warns() -> None:
    severity, metrics, summary = _evaluate_cloudflare_layer(
        {"url": "https://example.test/health", "status_code": 200, "error": None, "headers": {}},
        expect_cloudflare_proxy=True,
    )

    assert severity == SEV_WARNING
    assert metrics["proxy_mode"] == "expected_but_not_detected"
    assert metrics["proxy_detected"] is False
    assert "Cloudflare" in summary
