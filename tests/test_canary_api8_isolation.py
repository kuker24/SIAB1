from pathlib import Path
import json
import os
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_COMPOSE = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
CANARY_COMPOSE = (ROOT / "docker-compose.canary-api8.yml").read_text(encoding="utf-8")
NGINX_CONF = (ROOT / "docker" / "nginx.production.conf").read_text(encoding="utf-8")
STAGE0_API8 = (ROOT / "docker" / "nginx.canary-stage0.api8.line").read_text(encoding="utf-8")

CONTROL_SERVICES = ("api", "api2", "api3", "api4", "api5", "api6", "api7")
API_VOLUMES = (
    "./uploads:/app/uploads",
    "./logs:/app/logs",
    "./seb_configs:/app/seb_configs",
    "./static:/app/static",
    "./templates:/app/templates",
    "./apk_builds:/app/apk_builds",
    "./runtime_control:/app/runtime_control",
)


def test_canary_override_targets_only_api8() -> None:
    assert "api8:" in CANARY_COMPOSE
    for name in CONTROL_SERVICES + ("api_admin", "api_admin2"):
        assert re.search(rf"^\s+{name}:", CANARY_COMPOSE, re.MULTILINE) is None


def test_canary_api8_replaces_app_mount_and_pins_n4() -> None:
    assert "volumes: !override" in CANARY_COMPOSE
    assert "/opt/siab1-canary/app:/app/app" in CANARY_COMPOSE
    assert "./app:/app/app" not in CANARY_COMPOSE
    assert "START_DB_ADMISSION_LIMIT=4" in CANARY_COMPOSE
    assert "SIAB_REPLICA=api8" in CANARY_COMPOSE
    for volume in API_VOLUMES:
        assert volume in CANARY_COMPOSE


def test_production_control_plane_keeps_shared_app_mount() -> None:
    assert "./app:/app/app" in PRODUCTION_COMPOSE
    assert "/opt/siab1-canary/app:/app/app" not in PRODUCTION_COMPOSE
    api_block = PRODUCTION_COMPOSE.split("x-api-service: &api-service", 1)[1].split(
        "\n  api:", 1
    )[0]
    assert "START_DB_ADMISSION_LIMIT" not in api_block


def test_nginx_logs_upstream_identity_and_status_chain() -> None:
    assert "$upstream_addr" in NGINX_CONF
    assert "$upstream_status" in NGINX_CONF
    assert "$upstream_response_time" in NGINX_CONF
    assert "$upstream_http_x_siab_replica" in NGINX_CONF


def test_production_api8_is_not_down_by_default() -> None:
    match = re.search(r"server api8:8000[^\n]*", NGINX_CONF)
    assert match is not None
    assert " down" not in match.group(0)


def test_stage0_snippet_marks_api8_down() -> None:
    assert "server api8:8000" in STAGE0_API8
    assert " down" in STAGE0_API8
    assert "api_admin" not in STAGE0_API8


def test_resolved_compose_isolates_api8_app_mount() -> None:
    if shutil.which("docker") is None:
        return
    env = os.environ.copy()
    env.setdefault("SECRET_KEY", "canary-config-placeholder")
    env.setdefault("JWT_SECRET_KEY", "canary-config-jwt-placeholder")
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(ROOT / "docker-compose.production.yml"),
            "-f",
            str(ROOT / "docker-compose.canary-api8.yml"),
            "config",
            "--format",
            "json",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    services = json.loads(completed.stdout)["services"]

    def app_sources(name: str) -> list[str]:
        return [
            str(volume.get("source") or "")
            for volume in services[name].get("volumes") or []
            if volume.get("target") == "/app/app"
        ]

    def env_map(name: str) -> dict[str, str]:
        value = services[name].get("environment") or {}
        if isinstance(value, dict):
            return {str(key): str(item) for key, item in value.items()}
        parsed: dict[str, str] = {}
        for item in value:
            key, _, raw = str(item).partition("=")
            parsed[key] = raw
        return parsed

    assert app_sources("api8") == ["/opt/siab1-canary/app"]
    assert env_map("api8")["START_DB_ADMISSION_LIMIT"] == "4"
    assert env_map("api8")["SIAB_REPLICA"] == "api8"
    for name in ("api", "api2", "api3", "api4", "api5", "api6", "api7", "api_admin", "api_admin2"):
        sources = app_sources(name)
        assert len(sources) == 1
        assert sources[0].endswith("/app")
        assert "/opt/siab1-canary/app" not in sources
        mapped = env_map(name)
        assert mapped.get("START_DB_ADMISSION_LIMIT") != "4"
        assert mapped.get("SIAB_REPLICA") != "api8"
