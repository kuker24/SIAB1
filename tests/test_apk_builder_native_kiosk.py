from pathlib import Path

from tools.apk_builder_core.context import detect_project_context
from tools.apk_builder_core.native_kiosk import (
    DEFAULT_PRODUCTION_URL,
    NATIVE_KIOSK_PACKAGE,
    apply_native_kiosk_config,
    is_placeholder_server_url,
    kiosk_release_apk_path,
    load_optional_server_url,
    load_release_signing_env,
    read_native_kiosk_config,
    signing_env_ready,
    signing_status_text,
)


def test_placeholder_url_is_rejected() -> None:
    assert is_placeholder_server_url("https://siab1.invalid/")
    assert is_placeholder_server_url("https://siab1.invalid/student/")
    assert not is_placeholder_server_url(DEFAULT_PRODUCTION_URL)


def test_signing_env_loads_from_file_without_process_env(
    tmp_path: Path,
) -> None:
    keystore = tmp_path / "release.jks"
    keystore.write_bytes(b"jks")
    env_file = tmp_path / "siab1-release.env"
    env_file.write_text(
        "\n".join(
            [
                f"SIAB1_RELEASE_KEYSTORE={keystore}",
                "SIAB1_RELEASE_STORE_PASSWORD=not-logged",
                "SIAB1_RELEASE_KEY_ALIAS=siab1",
                "SIAB1_RELEASE_KEY_PASSWORD=not-logged",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_release_signing_env(env_file=env_file, environ={})

    assert signing_env_ready(loaded)
    assert loaded["SIAB1_RELEASE_KEY_ALIAS"] == "siab1"
    assert Path(loaded["SIAB1_RELEASE_KEYSTORE"]) == keystore


def test_process_env_overrides_signing_file(tmp_path: Path) -> None:
    keystore = tmp_path / "release.jks"
    keystore.write_bytes(b"jks")
    env_file = tmp_path / "siab1-release.env"
    env_file.write_text(
        "\n".join(
            [
                f"SIAB1_RELEASE_KEYSTORE={keystore}",
                "SIAB1_RELEASE_STORE_PASSWORD=file-pass",
                "SIAB1_RELEASE_KEY_ALIAS=from-file",
                "SIAB1_RELEASE_KEY_PASSWORD=file-pass",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_release_signing_env(
        env_file=env_file,
        environ={"SIAB1_RELEASE_KEY_ALIAS": "from-env"},
    )

    assert loaded["SIAB1_RELEASE_KEY_ALIAS"] == "from-env"


def test_detect_project_context_finds_native_kiosk() -> None:
    context = detect_project_context(Path("tools/apk_builder_gui.py"))

    assert context.kiosk_project.name == "android-kiosk"
    assert (context.kiosk_project / "app" / "build.gradle.kts").is_file()
    assert kiosk_release_apk_path(context.kiosk_project).name == "app-release.apk"


def test_gui_defaults_target_native_kiosk() -> None:
    from tools import apk_builder_gui as gui

    assert gui.NATIVE_KIOSK_PACKAGE == NATIVE_KIOSK_PACKAGE
    assert gui.DEFAULT_PRODUCTION_URL == DEFAULT_PRODUCTION_URL
    assert not is_placeholder_server_url(gui.DEFAULT_PRODUCTION_URL)


def test_optional_server_url_ignores_placeholder(tmp_path: Path) -> None:
    env_file = tmp_path / "siab1-release.env"
    env_file.write_text(
        "SIAB1_SERVER_URL=https://siab1.invalid/\n",
        encoding="utf-8",
    )
    loaded = load_optional_server_url(env_file=env_file, environ={})
    assert is_placeholder_server_url(loaded)

    production = load_optional_server_url(
        env_file=env_file,
        environ={"SIAB1_SERVER_URL": DEFAULT_PRODUCTION_URL},
    )
    assert production == DEFAULT_PRODUCTION_URL
    assert not is_placeholder_server_url(production)


def test_signing_status_hides_secrets(tmp_path: Path) -> None:
    missing = signing_status_text({})
    assert "siap" in missing
    assert "password" not in missing.lower()

    keystore = tmp_path / "release.jks"
    keystore.write_bytes(b"jks")
    ready = signing_status_text(
        {
            "SIAB1_RELEASE_KEYSTORE": str(keystore),
            "SIAB1_RELEASE_STORE_PASSWORD": "secret",
            "SIAB1_RELEASE_KEY_ALIAS": "siab1",
            "SIAB1_RELEASE_KEY_PASSWORD": "secret",
        }
    )
    assert ready == "Signing rilis: siap"
    assert "secret" not in ready


def test_apply_and_read_native_kiosk_config(tmp_path: Path) -> None:
    gradle = tmp_path / "app" / "build.gradle.kts"
    gradle.parent.mkdir(parents=True)
    gradle.write_text(
        'applicationId = "id.siab1.kiosk"\nversionCode = 4\nversionName = "2.0.2"\n',
        encoding="utf-8",
    )
    config_kt = tmp_path / "app/src/main/java/id/siab1/kiosk/AppConfig.kt"
    config_kt.parent.mkdir(parents=True)
    config_kt.write_text(
        'const val buildToken: String = "BUILD-OLD"\n'
        'const val appName: String = "OLD"\n',
        encoding="utf-8",
    )
    strings = tmp_path / "app/src/main/res/values/strings.xml"
    strings.parent.mkdir(parents=True)
    strings.write_text('<string name="app_name">OLD</string>\n', encoding="utf-8")

    apply_native_kiosk_config(
        tmp_path,
        version_name="2.0.3",
        version_code="5",
        app_name="SIAB1",
        build_token="BUILD-20260830120000-ABC123",
    )
    cfg = read_native_kiosk_config(tmp_path)

    assert cfg.package_name == NATIVE_KIOSK_PACKAGE
    assert cfg.version_name == "2.0.3"
    assert cfg.version_code == "5"
    assert cfg.app_name == "SIAB1"
    assert cfg.build_token == "BUILD-20260830120000-ABC123"
    assert "siab1.invalid" not in gradle.read_text(encoding="utf-8")
    assert '<string name="app_name">SIAB1</string>' in strings.read_text(
        encoding="utf-8"
    )


def test_detect_project_context_from_launcher() -> None:
    context = detect_project_context(Path("bin/run_apk_builder.sh"))
    assert context.kiosk_project.name == "android-kiosk"
