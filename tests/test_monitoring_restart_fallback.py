from pathlib import Path


MONITORING_API_SOURCE = Path("app/api/monitoring.py").read_text(encoding="utf-8")
MONITORING_TEMPLATE_SOURCE = Path("templates/admin/monitoring.html").read_text(encoding="utf-8")
MONITORING_PAGE_JS_SOURCE = Path("static/js/admin/monitoring.js").read_text(encoding="utf-8")


def test_ops_summary_includes_restart_backend_status() -> None:
    assert 'payload["restart_backend"] = _restart_backend_status()' in MONITORING_API_SOURCE


def test_monitoring_dashboard_has_safe_restart_fallback_copy() -> None:
    # Monitoring dashboard script moved from inline HTML to static JS.
    assert '/static/js/admin/monitoring.js?v=' in MONITORING_TEMPLATE_SOURCE
    assert "function getRestartBackendVisual(summary)" in MONITORING_PAGE_JS_SOURCE
    assert "Reset Runtime Antar Sesi" in MONITORING_PAGE_JS_SOURCE
    assert "Full restart backend belum dikonfigurasi aman pada API ini." in MONITORING_PAGE_JS_SOURCE
    assert "full_restart: restartBackendVisual.fullRestartAvailable" in MONITORING_PAGE_JS_SOURCE
