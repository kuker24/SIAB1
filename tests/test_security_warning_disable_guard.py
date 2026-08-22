from pathlib import Path
import re


VIOLATION_EVENTS_SOURCE = Path("app/api/violation_events.py").read_text(encoding="utf-8")
MONITORING_SOURCE = Path("app/api/monitoring.py").read_text(encoding="utf-8")
SCORING_SOURCE = Path("app/core/violation_scoring.py").read_text(encoding="utf-8")


def _extract_async_function(source: str, function_name: str) -> str:
    pattern = re.compile(
        rf"async def {re.escape(function_name)}\([\s\S]*?(?=\n@router|\nasync def |\ndef |\nclass |\Z)",
        re.MULTILINE,
    )
    match = pattern.search(source)
    assert match is not None, f"Function {function_name} not found"
    return match.group(0)


def test_security_warning_is_declared_as_disabled_violation_type() -> None:
    assert "VIOLATION_DISABLED_EVENT_TYPES" in SCORING_SOURCE
    assert '"violation_security_warning"' in SCORING_SOURCE
    assert '"violation_accessibility_risk"' in SCORING_SOURCE


def test_log_violation_ignores_security_warning_before_scoring_and_broadcast() -> None:
    fn = _extract_async_function(VIOLATION_EVENTS_SOURCE, "log_violation")
    assert "is_violation_event_disabled(normalized_event_type)" in fn
    assert "Ignored disabled violation event" in fn
    assert "return _ignored_violation_response(" in fn
    assert 'status="ignored"' in VIOLATION_EVENTS_SOURCE


def test_monitoring_queries_exclude_security_warning_from_counted_payloads() -> None:
    assert "VIOLATION_DISABLED_EVENT_TYPES" in MONITORING_SOURCE
    assert "notin_(disabled_types)" in MONITORING_SOURCE


def test_monitoring_queries_exclude_accessibility_risk_from_counted_payloads() -> None:
    assert '"violation_accessibility_risk"' in SCORING_SOURCE
