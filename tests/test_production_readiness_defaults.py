from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_SOURCE = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
COMPOSE_SOURCE = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
ENV_EXAMPLE_SOURCE = (ROOT / ".env.example").read_text(encoding="utf-8")


def test_answer_write_defaults_are_direct_and_queue_off() -> None:
    assert 'os.getenv("ANSWER_WRITE_MODE", "direct").lower()' in CONFIG_SOURCE
    assert 'os.getenv("ANSWER_QUEUE_ENABLED", "false").lower() == "true"' in CONFIG_SOURCE
    assert 'os.getenv("ANSWER_QUEUE_PERCENTAGE", "0")' in CONFIG_SOURCE

    assert "ANSWER_WRITE_MODE=direct" in ENV_EXAMPLE_SOURCE
    assert "ANSWER_QUEUE_ENABLED=false" in ENV_EXAMPLE_SOURCE
    assert "ANSWER_QUEUE_PERCENTAGE=0" in ENV_EXAMPLE_SOURCE

    assert "ANSWER_WRITE_MODE=${ANSWER_WRITE_MODE:-direct}" in COMPOSE_SOURCE
    assert "ANSWER_QUEUE_ENABLED=${ANSWER_QUEUE_ENABLED:-false}" in COMPOSE_SOURCE
    assert "ANSWER_QUEUE_PERCENTAGE=${ANSWER_QUEUE_PERCENTAGE:-0}" in COMPOSE_SOURCE


def test_mobile_first_security_defaults_stay_off_or_safe() -> None:
    assert 'os.getenv("MOBILE_APK_PRIMARY", "true").lower() == "true"' in CONFIG_SOURCE
    assert 'os.getenv("SEB_DESKTOP_LEGACY_ENABLED", "false").lower() == "true"' in CONFIG_SOURCE
    assert 'os.getenv("SEB_QR_ENABLED", "false").lower() == "true"' in CONFIG_SOURCE
    assert 'os.getenv("APK_BUILD_ENDPOINT_ENABLED", "false").lower() == "true"' in CONFIG_SOURCE
    assert 'os.getenv("TELEGRAM_ALERTING_ENABLED", "false").lower() == "true"' in CONFIG_SOURCE
    assert 'os.getenv("VIOLATION_ASYNC_ENABLED", "true").lower() == "true"' in CONFIG_SOURCE
    assert 'os.getenv(\n        "ADMIN_MONITORING_DETAIL_LEVEL",\n        "summary",\n    ).lower()' in CONFIG_SOURCE

    assert "MOBILE_APK_PRIMARY=${MOBILE_APK_PRIMARY:-true}" in COMPOSE_SOURCE
    assert "SEB_DESKTOP_LEGACY_ENABLED=${SEB_DESKTOP_LEGACY_ENABLED:-false}" in COMPOSE_SOURCE
    assert "SEB_QR_ENABLED=${SEB_QR_ENABLED:-false}" in COMPOSE_SOURCE
    assert "APK_BUILD_ENDPOINT_ENABLED=${APK_BUILD_ENDPOINT_ENABLED:-false}" in COMPOSE_SOURCE
    assert "TELEGRAM_ALERTING_ENABLED=${TELEGRAM_ALERTING_ENABLED:-false}" in COMPOSE_SOURCE
    assert "VIOLATION_ASYNC_ENABLED=${VIOLATION_ASYNC_ENABLED:-true}" in COMPOSE_SOURCE
    assert "ADMIN_MONITORING_DETAIL_LEVEL=${ADMIN_MONITORING_DETAIL_LEVEL:-summary}" in COMPOSE_SOURCE
    assert "ADMIN_MONITORING_DETAIL_LEVEL=summary" in ENV_EXAMPLE_SOURCE


def test_heavy_export_remains_runtime_configurable_for_peak_mode() -> None:
    assert 'os.getenv("HEAVY_EXPORT_ENABLED", "true").lower() == "true"' in CONFIG_SOURCE
    assert "HEAVY_EXPORT_ENABLED=${HEAVY_EXPORT_ENABLED:-false}" in COMPOSE_SOURCE
    assert "EXAM_PEAK_MODE=${EXAM_PEAK_MODE:-true}" in COMPOSE_SOURCE
    assert "HEAVY_EXPORT_ENABLED=false" in ENV_EXAMPLE_SOURCE
