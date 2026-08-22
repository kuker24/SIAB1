from pathlib import Path


ROOT = Path("flutter_client_code/android/app/src")


def test_release_manifest_disables_cleartext_traffic() -> None:
    manifest = (ROOT / "main/AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert 'android:usesCleartextTraffic="true"' not in manifest
    assert 'android:networkSecurityConfig="@xml/network_security_config"' in manifest


def test_release_network_security_config_disables_cleartext_and_user_ca() -> None:
    config = (ROOT / "main/res/xml/network_security_config.xml").read_text(encoding="utf-8")
    assert 'cleartextTrafficPermitted="false"' in config
    assert 'cleartextTrafficPermitted="true"' not in config
    assert '<certificates src="system" />' in config
    assert '<certificates src="user" />' not in config


def test_debug_and_profile_can_override_cleartext_for_local_testing() -> None:
    for build_type in ("debug", "profile"):
        manifest = (ROOT / f"{build_type}/AndroidManifest.xml").read_text(encoding="utf-8")
        config = (ROOT / f"{build_type}/res/xml/network_security_config.xml").read_text(
            encoding="utf-8"
        )
        assert 'android:usesCleartextTraffic="true"' in manifest
        assert 'tools:replace="android:usesCleartextTraffic,android:networkSecurityConfig"' in manifest
        assert 'cleartextTrafficPermitted="true"' in config
        assert '<certificates src="user" />' in config


def test_api_service_forces_https_when_config_enabled() -> None:
    config = Path("flutter_client_code/lib/config.dart").read_text(encoding="utf-8")
    source = Path("flutter_client_code/lib/services/api_service.dart").read_text(encoding="utf-8")

    assert 'static const bool forceHttps = true;' in config
    assert 'static const bool allowCleartextTraffic = false;' in config
    assert 'static const String serverUrl = "https://' in config
    assert 'static const String serverUrl = "http://' not in config
    assert "if (AppConfig.forceHttps && value.startsWith('http://'))" in source
    assert "value.replaceFirst('http://', 'https://')" in source


def test_release_signing_config_uses_uncommitted_key_properties_only() -> None:
    gradle = Path("flutter_client_code/android/app/build.gradle").read_text(encoding="utf-8")

    assert "rootProject.file('key.properties')" in gradle
    assert "keystoreProperties['storeFile']" in gradle
    assert ".jks" not in gradle
    assert ".keystore" not in gradle
    assert "storePassword \"" not in gradle
    assert "keyPassword \"" not in gradle
