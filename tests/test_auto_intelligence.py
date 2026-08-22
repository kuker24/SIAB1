from app.core.auto_intelligence import _compute_mode_decision, _need_healing, _should_allow_downgrade


def _summary_payload(
    *,
    mode: str = "normal",
    global_5xx: float = 0.0,
    auth_p95: float = 0.0,
    exam_start_p95: float = 0.0,
    submit_p95: float = 0.0,
    cpu: float = 20.0,
    db_conn: float = 20.0,
    redis_stability: float = 100.0,
    active_sessions: int = 0,
    backend_status: str = "healthy",
    database_status: str = "healthy",
    redis_status: str = "healthy",
    origin_status_code: int = 200,
):
    return {
        "policy": {
            "resource_mode": mode,
        },
        "key_metrics": {
            "global_5xx_percent": global_5xx,
            "auth_signin_p95_ms": auth_p95,
            "exam_start_p95_ms": exam_start_p95,
            "submit_answer_p95_ms": submit_p95,
            "cpu_percent": cpu,
            "db_connection_percent": db_conn,
            "redis_stability_score_percent": redis_stability,
        },
        "activity": {
            "active_sessions": active_sessions,
        },
        "layers": [
            {
                "id": "backend_api",
                "status": backend_status,
                "metrics": {
                    "origin_status_code": origin_status_code,
                },
            },
            {
                "id": "database",
                "status": database_status,
                "metrics": {},
            },
            {
                "id": "redis",
                "status": redis_status,
                "metrics": {},
            },
        ],
    }


def test_mode_decision_escalates_to_extreme_on_critical_runtime_pressure() -> None:
    summary = _summary_payload(
        mode="high",
        global_5xx=4.8,
        auth_p95=4100,
        exam_start_p95=3500,
        submit_p95=3900,
        cpu=88,
        db_conn=91,
        redis_stability=82,
        active_sessions=64,
        backend_status="critical",
        database_status="critical",
        redis_status="warning",
        origin_status_code=503,
    )

    decision = _compute_mode_decision(summary, current_mode="high", consecutive_relief_cycles=0)

    assert decision["target_mode"] == "extreme"
    assert decision["direction"] == "up"
    assert float(decision["confidence"]) >= 0.6
    assert float(decision["score"]) >= 65.0


def test_mode_decision_returns_normal_when_system_is_stable() -> None:
    summary = _summary_payload(
        mode="normal",
        global_5xx=0.0,
        auth_p95=420,
        exam_start_p95=510,
        submit_p95=640,
        cpu=31,
        db_conn=24,
        redis_stability=99,
        active_sessions=3,
        backend_status="healthy",
        database_status="healthy",
        redis_status="healthy",
        origin_status_code=200,
    )

    decision = _compute_mode_decision(summary, current_mode="normal", consecutive_relief_cycles=0)

    assert decision["target_mode"] == "normal"
    assert decision["direction"] == "steady"
    assert float(decision["score"]) < 30.0


def test_need_healing_when_backend_warning_with_high_errors() -> None:
    summary = _summary_payload(
        global_5xx=2.2,
        submit_p95=2900,
        backend_status="warning",
        origin_status_code=502,
        active_sessions=18,
    )

    should_heal, reason = _need_healing(summary)

    assert should_heal is True
    assert reason == "backend_api_warning_with_runtime_pressure"


def test_need_healing_false_when_system_is_healthy() -> None:
    summary = _summary_payload(
        global_5xx=0.1,
        submit_p95=450,
        backend_status="healthy",
        origin_status_code=200,
    )

    should_heal, reason = _need_healing(summary)

    assert should_heal is False
    assert reason == "no_heal_signal"


def test_downgrade_allowed_after_sustained_relief_even_with_medium_confidence() -> None:
    decision = {
        "score": 18.0,
        "thresholds": {"high": 45.0, "extreme": 78.0},
    }
    should_change = _should_allow_downgrade(
        current_mode="extreme",
        target_mode="normal",
        decision=decision,
        consecutive_relief_cycles=6,
        cooldown_over=True,
        confidence=0.51,
    )
    assert should_change is True


def test_downgrade_blocked_when_relief_is_short_and_confidence_low() -> None:
    decision = {
        "score": 32.0,
        "thresholds": {"high": 45.0, "extreme": 78.0},
    }
    should_change = _should_allow_downgrade(
        current_mode="extreme",
        target_mode="normal",
        decision=decision,
        consecutive_relief_cycles=2,
        cooldown_over=True,
        confidence=0.40,
    )
    assert should_change is False
