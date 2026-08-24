from pathlib import Path


LOAD_SCRIPT_SOURCE = Path("scripts/prod_concurrent_exam_load.py").read_text(encoding="utf-8")
VIOLATION_SCRIPT_SOURCE = Path("scripts/verify_violation_monitoring_rt.py").read_text(
    encoding="utf-8"
)


def test_phase_pass_checks_support_api_only_mode_without_compose_db_snapshot() -> None:
    assert "db_during_available = db_snapshot.get(\"available\", True) is not False" in LOAD_SCRIPT_SOURCE
    assert "phase_report[\"pass_checks\"] = pass_checks" in LOAD_SCRIPT_SOURCE
    assert "live_stats_after_submit.get(\"completed_participants\")" in LOAD_SCRIPT_SOURCE


def test_api_cleanup_has_batch_delete_fallback_to_batch_update() -> None:
    assert "soft_deactivate_batch_update" in LOAD_SCRIPT_SOURCE
    assert "\"PATCH\",\n                        \"/api/users/batch-update\"" in LOAD_SCRIPT_SOURCE


def test_phase_setup_tracks_exam_before_seb_configuration() -> None:
    assert "created_exam_ids.append(exam_id)" in LOAD_SCRIPT_SOURCE
    assert "created_exam_ids=exam_ids" in LOAD_SCRIPT_SOURCE


def test_load_supports_production_with_legacy_seb_disabled() -> None:
    assert 'detail.get("feature") == "seb_desktop_legacy"' in LOAD_SCRIPT_SOURCE
    assert "'configKey', seb_config_key" in LOAD_SCRIPT_SOURCE


def test_violation_smoke_accepts_async_queue_contract() -> None:
    assert "response.status_code not in {200, 202}" in VIOLATION_SCRIPT_SOURCE
    assert 'response_payload.get("status") == "ignored"' in VIOLATION_SCRIPT_SOURCE
    assert "for expected in expected_monitoring_keys" in VIOLATION_SCRIPT_SOURCE
