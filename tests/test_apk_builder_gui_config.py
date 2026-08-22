from tools.apk_builder_gui import (
    extract_runtime_tuning_from_config,
    normalize_apk_display_name,
    render_config_dart_content,
    validate_generated_config_text,
)


BASE_RENDER_KWARGS = {
    "normalized_url": "https://siab1.invalid/",
    "app_name": "SIAB1",
    "force_https": True,
    "cleartext_allowed": False,
    "build_mode": "universal_apk",
    "build_token": "BUILD-20260430170000-ABC123",
    "build_timestamp": 1772876093,
    "security_settings": {
        "enable_kiosk": True,
        "block_screenshot": True,
        "detect_root": True,
        "block_task_switch": True,
    },
    "generated_at": "2026-04-30 17:00:00",
}


def test_ux_offline_first_generator_uses_current_performance_tuning():
    content, profile, tuning = render_config_dart_content(
        **BASE_RENDER_KWARGS,
        resilience_profile="ux_offline_first",
    )

    assert profile == "ux_offline_first"
    assert tuning["reconnect_probe_interval_seconds"] == 10
    assert tuning["answer_journal_sync_interval_seconds"] == 8
    assert "reconnectProbeIntervalSeconds = 10;" in content
    assert "answerJournalSyncIntervalSeconds = 8;" in content
    assert 'static const String appName = "SIAB1";' in content
    assert 'static const String appSubtitle = "Sistem Informasi Asesmen Berintegritas";' in content

    is_valid, errors = validate_generated_config_text(
        content,
        expected_profile="ux_offline_first",
    )
    assert is_valid, errors


def test_generated_config_keeps_siab1_display_name():
    siab1_kwargs = dict(BASE_RENDER_KWARGS)
    siab1_kwargs["app_name"] = "SIAB1"

    content, _, _ = render_config_dart_content(
        **siab1_kwargs,
        resilience_profile="ux_offline_first",
    )

    assert normalize_apk_display_name("SIAB1 MAN 1 Rokan Hulu") == "SIAB1 MAN 1 Rokan Hulu"
    assert 'static const String appName = "SIAB1";' in content
    assert "Ujian " "Online" not in content


def test_ux_offline_first_generator_prevents_old_timing_rollback():
    content, profile, tuning = render_config_dart_content(
        **BASE_RENDER_KWARGS,
        resilience_profile="ux_offline_first",
        runtime_overrides={
            "reconnect_probe_interval_seconds": 6,
            "answer_journal_sync_interval_seconds": 6,
        },
    )

    assert profile == "ux_offline_first"
    assert tuning["reconnect_probe_interval_seconds"] == 10
    assert tuning["answer_journal_sync_interval_seconds"] == 8

    parsed_tuning = extract_runtime_tuning_from_config(content)
    assert parsed_tuning["reconnect_probe_interval_seconds"] == 10
    assert parsed_tuning["answer_journal_sync_interval_seconds"] == 8


def test_generated_config_guard_rejects_stale_ux_offline_first_values():
    content, _, _ = render_config_dart_content(
        **BASE_RENDER_KWARGS,
        resilience_profile="ux_offline_first",
    )
    stale_content = content.replace(
        "reconnectProbeIntervalSeconds = 10;",
        "reconnectProbeIntervalSeconds = 6;",
    ).replace(
        "answerJournalSyncIntervalSeconds = 8;",
        "answerJournalSyncIntervalSeconds = 6;",
    )

    is_valid, errors = validate_generated_config_text(
        stale_content,
        expected_profile="ux_offline_first",
    )

    assert not is_valid
    assert any("reconnectProbeIntervalSeconds minimal 10" in error for error in errors)
    assert any("answerJournalSyncIntervalSeconds minimal 8" in error for error in errors)
