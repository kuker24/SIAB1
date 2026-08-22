import pytest
from fastapi import HTTPException

from app.config import Settings, settings
from app.core.feature_flags import require_feature_enabled
from app.api import apk, exam_seb, seb_autoconfig, users
from app.utils.telegram_alerts import send_test_alert


def _settings_for_test(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "secret_key": "test-secret-key",
        "database_url": "postgresql+asyncpg://user:pass@localhost/db",
    }
    values.update(overrides)
    return Settings(**values)


def test_mobile_first_flags_defaults_are_safe() -> None:
    cfg = _settings_for_test()

    assert cfg.mobile_apk_primary is True
    assert cfg.seb_desktop_legacy_enabled is False
    assert cfg.seb_qr_enabled is False
    assert cfg.seb_debug_endpoints_enabled is False
    assert cfg.apk_build_endpoint_enabled is False
    assert cfg.telegram_alerting_enabled is False
    assert cfg.heavy_export_enabled is True
    assert cfg.exam_peak_mode is False
    assert cfg.admin_monitoring_detail_level == "summary"
    assert cfg.violation_async_enabled is True
    assert cfg.answer_sync_internal_service is True
    assert cfg.answer_write_mode == "direct"
    assert cfg.answer_queue_enabled is False
    assert cfg.answer_queue_percentage == 0
    assert cfg.heavy_exports_active is True


def test_invalid_admin_monitoring_detail_level_is_rejected() -> None:
    with pytest.raises(ValueError, match="ADMIN_MONITORING_DETAIL_LEVEL"):
        _settings_for_test(admin_monitoring_detail_level="verbose")


def test_invalid_answer_queue_percentage_is_rejected() -> None:
    with pytest.raises(ValueError, match="ANSWER_QUEUE_PERCENTAGE"):
        _settings_for_test(answer_queue_percentage=101)


def test_require_feature_enabled_raises_consistent_disabled_payload() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_feature_enabled(False, "legacy_feature")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["error"] == "FEATURE_DISABLED"
    assert exc_info.value.detail["feature"] == "legacy_feature"


@pytest.mark.asyncio
async def test_seb_desktop_download_config_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "seb_desktop_legacy_enabled", False)

    with pytest.raises(HTTPException) as exc_info:
        await seb_autoconfig.download_dynamic_seb_config(None)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["feature"] == "seb_desktop_legacy"


@pytest.mark.asyncio
async def test_public_seb_desktop_config_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "seb_desktop_legacy_enabled", False)

    with pytest.raises(HTTPException) as exc_info:
        await exam_seb.download_default_seb_config()

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["feature"] == "seb_desktop_legacy"


@pytest.mark.asyncio
async def test_public_seb_desktop_config_still_available_when_legacy_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "seb_desktop_legacy_enabled", True)

    response = await exam_seb.download_default_seb_config()

    assert response.media_type == "application/seb"
    assert f"{settings.base_url}/student/".encode() in response.body


@pytest.mark.asyncio
async def test_seb_qr_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "seb_qr_enabled", False)

    with pytest.raises(HTTPException) as exc_info:
        await exam_seb.get_seb_qrcode()

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["feature"] == "seb_qr"


@pytest.mark.asyncio
async def test_seb_qr_still_available_when_legacy_qr_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "seb_qr_enabled", True)

    response = await exam_seb.get_seb_qrcode(url="https://example.test/api/exams/default-seb-config.seb")

    assert response.media_type == "image/png"


@pytest.mark.asyncio
async def test_apk_build_endpoint_disabled_without_blocking_apk_info(monkeypatch) -> None:
    monkeypatch.setattr(settings, "apk_build_endpoint_enabled", False)

    with pytest.raises(HTTPException) as exc_info:
        await apk.legacy_build_apk(
            app_name="SIAB1",
            package_name="com.school.examapp",
            server_url="https://example.test",
            build_mode="universal_apk",
            icon=None,
            current_user=None,
            db=None,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["feature"] == "apk_build_endpoint"


@pytest.mark.asyncio
async def test_telegram_alerting_disabled_by_feature_flag(monkeypatch) -> None:
    monkeypatch.setattr(settings, "telegram_enabled", True)
    monkeypatch.setattr(settings, "telegram_alerting_enabled", False)
    monkeypatch.setattr(settings, "telegram_bot_token", "dummy-token")
    monkeypatch.setattr(settings, "telegram_chat_ids", "123")

    success, message = await send_test_alert()

    assert success is False
    assert "disabled" in message.lower()


@pytest.mark.asyncio
async def test_heavy_export_disabled_during_exam_peak(monkeypatch) -> None:
    monkeypatch.setattr(settings, "heavy_export_enabled", True)
    monkeypatch.setattr(settings, "exam_peak_mode", True)

    with pytest.raises(HTTPException) as exc_info:
        await users.export_users(filters=None, format="csv", current_user=None, db=None)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["feature"] == "heavy_export"
