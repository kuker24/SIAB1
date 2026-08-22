from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_dockerignore_excludes_secrets_and_large_runtime_artifacts() -> None:
    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {
        ".env",
        ".env.*",
        "docker/certs/*",
        ".git",
        ".venv",
        "reports",
        "recovery_sistem",
        "apk_builds",
        "flutter_client_code/build",
    } <= ignored
    assert "!.env.example" in ignored
    assert "!docker/init.sql" in ignored
    assert "!app/migrations/*.sql" in ignored


def test_all_production_services_have_bounded_json_log_rotation() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))

    for service_name, service in compose["services"].items():
        logging = service.get("logging")
        assert logging, f"{service_name} has no logging policy"
        assert logging["driver"] == "json-file"
        assert str(logging["options"]["max-size"]) == "20m"
        assert str(logging["options"]["max-file"]) == "5"


def test_safeline_is_the_only_public_http_ingress() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    nginx = compose["services"]["nginx"]

    assert nginx["ports"] == ["127.0.0.1:${SIAB1_ORIGIN_PORT:-8080}:80"]
    assert not any("/etc/nginx/certs" in volume for volume in nginx["volumes"])

    safeline = yaml.safe_load(
        (ROOT / "infrastructure" / "safeline" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
    )
    assert safeline["services"]["mgt"]["ports"] == [
        "127.0.0.1:${SAFELINE_MGT_PORT:-9443}:1443"
    ]
    assert safeline["services"]["tengine"]["network_mode"] == "host"

    nginx_source = (ROOT / "docker" / "nginx.production.conf").read_text(encoding="utf-8")
    assert "listen 80 default_server;" in nginx_source
    assert "listen 443" not in nginx_source
    assert "ssl_certificate" not in nginx_source
    assert "proxy_set_header X-Forwarded-Proto $client_scheme;" in nginx_source


def test_production_dockerfile_uses_builder_and_excludes_build_toolchain_from_runtime() -> None:
    source = (ROOT / "docker" / "Dockerfile.production").read_text(encoding="utf-8")
    runtime_source = source[source.index("FROM python:3.11-slim AS runtime") :]
    runtime_requirements = (ROOT / "requirements.runtime.lock").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim AS builder" in source
    assert "python -m pip wheel" in source
    assert "COPY --from=builder /wheels /wheels" in source
    assert "requirements.runtime.lock" in source
    assert "build-essential" not in runtime_source
    assert "python3-dev" not in runtime_source
    assert '"pandas>=2.0.0"' not in source
    assert "pip install Cython" not in source
    assert "--no-index --find-links=/wheels" in runtime_source
    assert "pytest==" not in runtime_requirements
    assert "pytest-asyncio==" not in runtime_requirements
    assert "pip-audit==" not in runtime_requirements


def test_production_hardening_workflow_runs_blocking_checks() -> None:
    source = (ROOT / ".github" / "workflows" / "production-hardening.yml").read_text(
        encoding="utf-8"
    )

    assert "python -m pip_audit --requirement requirements.txt" in source
    assert "python -m pip_audit --requirement requirements.runtime.lock" in source
    assert "tests/test_p0_operational_hardening.py" in source
    assert "docker compose -f docker-compose.production.yml config --quiet" in source
    assert "docker build --file docker/Dockerfile.production" in source
    assert "continue-on-error" not in source


def test_production_defaults_protect_exam_peak_capacity() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))

    for service_name in ("api", "celery_worker"):
        environment = set(compose["services"][service_name]["environment"])
        assert "EXAM_PEAK_MODE=${EXAM_PEAK_MODE:-true}" in environment
        assert "HEAVY_EXPORT_ENABLED=${HEAVY_EXPORT_ENABLED:-false}" in environment

    refresher_source = (ROOT / "app" / "tasks" / "views_refresher.py").read_text(
        encoding="utf-8"
    )
    assert "if settings.exam_peak_mode:" in refresher_source
    assert '"status": "skipped", "reason": "exam_peak_mode"' in refresher_source


def test_internal_metrics_cover_all_api_replicas_and_public_proxy_blocks_metrics() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text(encoding="utf-8"))
    api_environment = set(compose["services"]["api"]["environment"])
    prometheus = yaml.safe_load((ROOT / "monitoring" / "prometheus.yml").read_text(encoding="utf-8"))
    nginx_source = (ROOT / "docker" / "nginx.production.conf").read_text(encoding="utf-8")

    assert "METRICS_BEARER_TOKEN=" in api_environment
    assert "METRICS_ALLOW_UNAUTHENTICATED=${METRICS_ALLOW_UNAUTHENTICATED:-true}" in api_environment
    assert "PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc" in api_environment

    fastapi_job = next(job for job in prometheus["scrape_configs"] if job["job_name"] == "fastapi")
    targets = {
        target
        for static_config in fastapi_job["static_configs"]
        for target in static_config["targets"]
    }
    assert targets == {
        "api:8000",
        "api2:8000",
        "api3:8000",
        "api4:8000",
        "api5:8000",
        "api6:8000",
        "api7:8000",
        "api8:8000",
        "api_admin:8000",
        "api_admin2:8000",
    }
    assert "location ^~ /metrics" in nginx_source
    assert "return 404;" in nginx_source[nginx_source.index("location ^~ /metrics") :]

    metrics_source = (ROOT / "app" / "api" / "metrics.py").read_text(encoding="utf-8")
    entrypoint_source = (ROOT / "docker" / "docker-entrypoint.sh").read_text(
        encoding="utf-8"
    )
    assert "multiprocess.MultiProcessCollector(output_registry)" in metrics_source
    assert "CollectorRegistry()" in metrics_source
    assert "prepare_prometheus_multiprocess" in entrypoint_source
    assert "-name '*.db' -delete" in entrypoint_source


def test_performance_middleware_exports_bounded_prometheus_metrics() -> None:
    source = (ROOT / "app" / "middleware" / "performance_monitoring.py").read_text(
        encoding="utf-8"
    )

    assert "canonicalize_endpoint(path)" in source
    assert "record_prometheus_request(" in source
    assert "duration_ms / 1000.0" in source
    assert "endpoint=path" not in source


def test_capacity_snapshot_script_is_read_only_and_bounded() -> None:
    source = (ROOT / "scripts" / "vps_capacity_snapshot_readonly.sh").read_text(
        encoding="utf-8"
    )
    forbidden = (
        " compose down",
        " compose up",
        "docker restart",
        "docker system prune",
        "redis-cli FLUSH",
        "DELETE FROM",
        "UPDATE ",
        "INSERT INTO",
        "DROP ",
        "TRUNCATE ",
        "pg_terminate_backend",
    )

    for marker in forbidden:
        assert marker not in source
    assert "docker stats --no-stream" in source
    assert 'INCLUDE_DIRECTORY_SIZES="${INCLUDE_DIRECTORY_SIZES:-false}"' in source
    assert "SHOW POOLS;" in source
    assert "SHOW STATS;" in source


def test_monitor_and_restore_resolve_repository_root() -> None:
    monitor_source = (ROOT / "bin" / "health-monitor.sh").read_text(encoding="utf-8")
    restore_source = (ROOT / "bin" / "restore.sh").read_text(encoding="utf-8")

    assert 'PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"' in monitor_source
    assert 'cd "$PROJECT_ROOT"' in monitor_source
    assert 'BACKUP_DIR="${BACKUP_ROOT:-${PROJECT_ROOT}/recovery_sistem}"' in monitor_source

    assert 'PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"' in restore_source
    assert 'cd "$PROJECT_ROOT"' in restore_source
    assert 'BACKUP_SCRIPT="${PROJECT_ROOT}/bin/backup-comprehensive.sh"' in restore_source
    assert "Restore aborted before stopping services or replacing data." in restore_source
    assert 'BACKUP_ROOT="$BACKUP_DIR" "$BACKUP_SCRIPT"' in restore_source
