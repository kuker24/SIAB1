from types import SimpleNamespace

from app.core.session_recovery import (
    RECOVERY_CATEGORY_ADMIN,
    RECOVERY_CATEGORY_CHEATING,
    RECOVERY_CATEGORY_NETWORK,
    RECOVERY_CATEGORY_SUBMITTED,
    evaluate_session_recovery,
)


def test_in_progress_session_is_resumable() -> None:
    session = SimpleNamespace(status="in_progress", terminated_by_admin=False, violation_count=0)
    result = evaluate_session_recovery(session, [])
    assert result["category"] == RECOVERY_CATEGORY_NETWORK
    assert result["allow_continue"] is True


def test_terminated_by_admin_is_blocked() -> None:
    session = SimpleNamespace(status="terminated", terminated_by_admin=True, violation_count=0)
    result = evaluate_session_recovery(session, [])
    assert result["category"] == RECOVERY_CATEGORY_ADMIN
    assert result["allow_continue"] is False


def test_force_submit_violation_blocks_recovery() -> None:
    session = SimpleNamespace(status="submitted", terminated_by_admin=False, violation_count=5)
    logs = [
        SimpleNamespace(event_type="EXAM_SUBMITTED", event_data={"force_submit": True})
    ]
    result = evaluate_session_recovery(session, logs)
    assert result["category"] == RECOVERY_CATEGORY_CHEATING
    assert result["allow_continue"] is False


def test_manual_submit_without_violation_is_not_recoverable_but_not_cheating() -> None:
    session = SimpleNamespace(status="submitted", terminated_by_admin=False, violation_count=0)
    logs = [SimpleNamespace(event_type="EXAM_SUBMITTED", event_data={"force_submit": False})]
    result = evaluate_session_recovery(session, logs)
    assert result["category"] == RECOVERY_CATEGORY_SUBMITTED
    assert result["allow_continue"] is False


def test_manual_reset_log_does_not_mark_admin_block_for_network_termination() -> None:
    session = SimpleNamespace(status="terminated", terminated_by_admin=False, violation_count=0)
    logs = [SimpleNamespace(event_type="SESSION_MANUAL_RESET", event_data={})]
    result = evaluate_session_recovery(session, logs)
    assert result["category"] == RECOVERY_CATEGORY_NETWORK
    assert result["allow_continue"] is True
