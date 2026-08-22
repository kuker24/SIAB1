from pathlib import Path


MONITORING_SOURCE = Path("app/api/monitoring.py").read_text(encoding="utf-8")


def test_restart_safe_has_distributed_exec_lock_guard() -> None:
    assert "RESTART_SAFE_EXEC_LOCK_KEY" in MONITORING_SOURCE
    assert "RESTART_ALREADY_IN_PROGRESS" in MONITORING_SOURCE
    assert "_acquire_restart_safe_exec_lock(current_user.username)" in MONITORING_SOURCE


def test_restart_safe_has_full_restart_cooldown_guard() -> None:
    assert "RESTART_SAFE_FULL_COOLDOWN_SECONDS" in MONITORING_SOURCE
    assert "RESTART_COOLDOWN_ACTIVE" in MONITORING_SOURCE
    assert '"cooldown": cooldown_state' in MONITORING_SOURCE
