from pathlib import Path


LOAD_SCRIPT_SOURCE = Path("scripts/prod_concurrent_exam_load.py").read_text(encoding="utf-8")


def test_phase_pass_checks_support_api_only_mode_without_compose_db_snapshot() -> None:
    assert "db_during_available = db_snapshot.get(\"available\", True) is not False" in LOAD_SCRIPT_SOURCE
    assert "phase_report[\"pass_checks\"] = pass_checks" in LOAD_SCRIPT_SOURCE
    assert "live_stats_after_submit.get(\"completed_participants\")" in LOAD_SCRIPT_SOURCE


def test_api_cleanup_has_batch_delete_fallback_to_batch_update() -> None:
    assert "soft_deactivate_batch_update" in LOAD_SCRIPT_SOURCE
    assert "\"PATCH\",\n                        \"/api/users/batch-update\"" in LOAD_SCRIPT_SOURCE
