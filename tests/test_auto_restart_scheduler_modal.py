from pathlib import Path


MONITORING_TEMPLATE_SOURCE = Path("templates/admin/monitoring.html").read_text(encoding="utf-8")
MONITORING_PAGE_JS_SOURCE = Path("static/js/admin/monitoring.js").read_text(encoding="utf-8")


def test_auto_restart_scheduler_uses_modal_editor() -> None:
    assert 'id="ops-auto-restart-modal"' in MONITORING_TEMPLATE_SOURCE
    assert "Tambah Jadwal" in MONITORING_TEMPLATE_SOURCE
    assert "function saveOpsAutoRestartSchedule()" in MONITORING_PAGE_JS_SOURCE
    assert "function shiftOpsAutoRestartParts(parts, offsetMinutes = 30)" in MONITORING_PAGE_JS_SOURCE


def test_auto_restart_scheduler_save_stays_synced_with_restart_backend() -> None:
    assert "full_restart: restartBackendVisual.fullRestartAvailable" in MONITORING_PAGE_JS_SOURCE
    assert "include_data_services: restartBackendVisual.fullRestartAvailable" in MONITORING_PAGE_JS_SOURCE
    assert "replace_runs: true" in MONITORING_PAGE_JS_SOURCE
    assert "Scheduler ini akan menjalankan jalur full restart antar sesi" in MONITORING_PAGE_JS_SOURCE
