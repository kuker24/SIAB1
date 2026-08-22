from pathlib import Path


MONITORING_SOURCE = Path("app/api/monitoring.py").read_text(encoding="utf-8")
MONITORING_RESTART_SOURCE = Path("app/api/monitoring_restart.py").read_text(encoding="utf-8")
COMPOSE_SOURCE = Path("docker-compose.production.yml").read_text(encoding="utf-8")
INSTALLER_SOURCE = Path("scripts/install_host_full_restart_systemd.sh").read_text(encoding="utf-8")
WORKER_SOURCE = Path("scripts/host_full_restart_worker.py").read_text(encoding="utf-8")


def test_monitoring_supports_signal_control_full_restart() -> None:
    # Restart-control internals were extracted to monitoring_restart.py.
    assert 'FULL_RESTART_REQUEST_FILE_ENV = "SYSTEM_FULL_RESTART_REQUEST_FILE"' in MONITORING_RESTART_SOURCE
    assert 'FULL_RESTART_STATUS_FILE_ENV = "SYSTEM_FULL_RESTART_STATUS_FILE"' in MONITORING_RESTART_SOURCE
    assert "async def _execute_full_restart_via_signal(" in MONITORING_RESTART_SOURCE
    assert '"mode": "host_signal"' in MONITORING_RESTART_SOURCE
    assert "_execute_full_restart(" in MONITORING_SOURCE


def test_compose_mounts_runtime_control_for_api() -> None:
    assert "- SYSTEM_FULL_RESTART_REQUEST_FILE=${SYSTEM_FULL_RESTART_REQUEST_FILE:-}" in COMPOSE_SOURCE
    assert "- SYSTEM_FULL_RESTART_STATUS_FILE=${SYSTEM_FULL_RESTART_STATUS_FILE:-}" in COMPOSE_SOURCE
    assert "- ./runtime_control:/app/runtime_control" in COMPOSE_SOURCE


def test_host_restart_worker_and_installer_exist() -> None:
    assert "STATELESS_SERVICES = [" in WORKER_SOURCE
    assert "systemctl enable --now" in INSTALLER_SOURCE
    assert "ExecStart=/usr/bin/python3" in INSTALLER_SOURCE


def test_full_restart_service_lists_cover_all_api_planes() -> None:
    required_services = [
        "api",
        "api2",
        "api3",
        "api4",
        "api5",
        "api6",
        "api7",
        "api8",
        "api_admin",
        "api_admin2",
    ]
    for service in required_services:
        assert f'"{service}"' in MONITORING_RESTART_SOURCE
        assert f'"{service}"' in WORKER_SOURCE
