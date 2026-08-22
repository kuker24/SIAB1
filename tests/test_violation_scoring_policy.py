import asyncio
from datetime import datetime, timezone

from app.core.violation_scoring import (
    is_violation_event_disabled,
    should_count_violation_for_score,
)


def test_is_violation_event_disabled_covers_configured_types() -> None:
    assert is_violation_event_disabled("violation_security_warning") is True
    assert is_violation_event_disabled("violation_accessibility_risk") is True
    assert is_violation_event_disabled("violation_tab_switch") is False


def test_non_scoring_focus_lost_is_warning_only() -> None:
    should_count, policy = asyncio.run(
        should_count_violation_for_score(
            db=None,  # type: ignore[arg-type]
            session_id=1,
            normalized_event_type="violation_focus_lost",
            violation_payload={},
            reported_at=datetime.now(timezone.utc),
        )
    )
    assert should_count is False
    assert policy == "violation_focus_lost_warning_only"


def test_tab_switch_with_duration_threshold_is_counted_without_db_lookup() -> None:
    should_count, policy = asyncio.run(
        should_count_violation_for_score(
            db=None,  # type: ignore[arg-type]
            session_id=1,
            normalized_event_type="violation_tab_switch",
            violation_payload={"duration_seconds": 4},
            reported_at=datetime.now(timezone.utc),
        )
    )
    assert should_count is True
    assert policy == "tab_switch_duration_threshold"


def test_accessibility_vendor_allowlist_is_warning_only_without_db_lookup() -> None:
    should_count, policy = asyncio.run(
        should_count_violation_for_score(
            db=None,  # type: ignore[arg-type]
            session_id=1,
            normalized_event_type="violation_accessibility_risk",
            violation_payload={
                "details": "Accessibility service mencurigakan: com.samsung.accessibility/.assistantmenu.serviceframework.AssistantMenuService",
            },
            reported_at=datetime.now(timezone.utc),
        )
    )
    assert should_count is False
    assert policy == "accessibility_vendor_allowlist"
