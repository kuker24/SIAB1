from pathlib import Path


MONITORING_API_SOURCE = Path("app/api/monitoring.py").read_text(encoding="utf-8")
MONITORING_TEMPLATE_SOURCE = Path("templates/admin/monitoring.html").read_text(encoding="utf-8")
API_CLIENT_SOURCE = Path("static/js/api.js").read_text(encoding="utf-8")


def test_monitoring_api_exposes_auto_intelligence_endpoints() -> None:
    assert '"/system/auto-intelligence"' in MONITORING_API_SOURCE
    assert '"/system/auto-intelligence/run"' in MONITORING_API_SOURCE


def test_monitoring_dashboard_has_auto_mode_and_healing_controls() -> None:
    assert "id=\"ops-auto-mode-btn\"" in MONITORING_TEMPLATE_SOURCE
    assert "id=\"ops-auto-heal-btn\"" in MONITORING_TEMPLATE_SOURCE
    assert "id=\"ops-auto-heal-run-btn\"" in MONITORING_TEMPLATE_SOURCE
    assert "toggleAutoModeFromOps" in MONITORING_TEMPLATE_SOURCE
    assert "toggleAutoHealingFromOps" in MONITORING_TEMPLATE_SOURCE
    assert "runAutoHealingNowFromOps" in MONITORING_TEMPLATE_SOURCE


def test_api_client_has_auto_intelligence_helpers() -> None:
    assert "getAutoIntelligenceStatus" in API_CLIENT_SOURCE
    assert "updateAutoIntelligenceControl" in API_CLIENT_SOURCE
    assert "runAutoIntelligence" in API_CLIENT_SOURCE
