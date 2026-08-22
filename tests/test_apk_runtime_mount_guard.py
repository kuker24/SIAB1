from pathlib import Path


COMPOSE_SOURCE = Path("docker-compose.production.yml").read_text(encoding="utf-8")


def test_api_services_mount_apk_builds_for_current_apk_downloads() -> None:
    assert "./apk_builds:/app/apk_builds" in COMPOSE_SOURCE
