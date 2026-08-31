"""Native android-kiosk helpers for the APK builder GUI."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from .validators import load_properties_file

NATIVE_KIOSK_PACKAGE = "id.siab1.kiosk"
DEFAULT_PRODUCTION_URL = "https://siab.man1rokanhulu.cloud/"
PLACEHOLDER_HOST = "siab1.invalid"
SIGNING_ENV_KEYS = (
    "SIAB1_RELEASE_KEYSTORE",
    "SIAB1_RELEASE_STORE_PASSWORD",
    "SIAB1_RELEASE_KEY_ALIAS",
    "SIAB1_RELEASE_KEY_PASSWORD",
)
DEFAULT_SIGNING_ENV_FILE = Path.home() / ".android" / "siab1-release.env"


@dataclass(frozen=True)
class NativeKioskConfig:
    package_name: str
    version_name: str
    version_code: str
    app_name: str
    build_token: str


def is_placeholder_server_url(raw_url: str) -> bool:
    host = (urlparse((raw_url or "").strip()).hostname or "").lower()
    return host == PLACEHOLDER_HOST or host.endswith("." + PLACEHOLDER_HOST)


def load_release_signing_env(
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Load signing vars from process env, then optional env file. Never log values."""
    source = dict(environ if environ is not None else os.environ)
    file_props: dict[str, str] = {}
    path = Path(env_file) if env_file is not None else DEFAULT_SIGNING_ENV_FILE
    if path.is_file():
        file_props = load_properties_file(path)
    loaded: dict[str, str] = {}
    for key in SIGNING_ENV_KEYS:
        value = str(source.get(key) or file_props.get(key) or "").strip()
        if value:
            loaded[key] = value
    return loaded


def load_optional_server_url(
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    source = dict(environ if environ is not None else os.environ)
    value = str(source.get("SIAB1_SERVER_URL") or "").strip()
    if value:
        return value
    path = Path(env_file) if env_file is not None else DEFAULT_SIGNING_ENV_FILE
    if path.is_file():
        props = load_properties_file(path)
        return str(props.get("SIAB1_SERVER_URL") or "").strip()
    return ""


def signing_env_ready(signing: Mapping[str, str]) -> bool:
    if not all(str(signing.get(key) or "").strip() for key in SIGNING_ENV_KEYS):
        return False
    return Path(signing["SIAB1_RELEASE_KEYSTORE"]).expanduser().is_file()


def signing_status_text(signing: Mapping[str, str]) -> str:
    if signing_env_ready(signing):
        return "Signing rilis: siap"
    return "Signing rilis: belum siap (~/.android/siab1-release.env)"


def kiosk_release_apk_path(kiosk_project: Path) -> Path:
    return (
        Path(kiosk_project)
        / "app"
        / "build"
        / "outputs"
        / "apk"
        / "release"
        / "app-release.apk"
    )


def read_native_kiosk_config(kiosk_project: Path) -> NativeKioskConfig:
    gradle = Path(kiosk_project) / "app" / "build.gradle.kts"
    content = gradle.read_text(encoding="utf-8") if gradle.is_file() else ""
    pkg = re.search(r'applicationId\s*=\s*"([^"]+)"', content)
    name = re.search(r'versionName\s*=\s*"([^"]+)"', content)
    code = re.search(r'versionCode\s*=\s*(\d+)', content)
    config_kt = Path(kiosk_project) / "app/src/main/java/id/siab1/kiosk/AppConfig.kt"
    kt = config_kt.read_text(encoding="utf-8") if config_kt.is_file() else ""
    token = re.search(r'const val buildToken: String = "([^"]+)"', kt)
    app_name = re.search(r'const val appName: String = "([^"]+)"', kt)
    return NativeKioskConfig(
        package_name=pkg.group(1) if pkg else NATIVE_KIOSK_PACKAGE,
        version_name=name.group(1) if name else "",
        version_code=code.group(1) if code else "",
        app_name=app_name.group(1) if app_name else "SIAB1",
        build_token=token.group(1) if token else "",
    )


def apply_native_kiosk_config(
    kiosk_project: Path,
    *,
    version_name: str,
    version_code: str,
    app_name: str,
    build_token: str,
) -> None:
    safe_name = (app_name or "SIAB1").replace('"', "")
    gradle = Path(kiosk_project) / "app" / "build.gradle.kts"
    if gradle.is_file():
        content = gradle.read_text(encoding="utf-8")
        content = re.sub(
            r'versionName\s*=\s*"[^"]+"',
            f'versionName = "{version_name}"',
            content,
            count=1,
        )
        content = re.sub(
            r'versionCode\s*=\s*\d+',
            f'versionCode = {version_code}',
            content,
            count=1,
        )
        gradle.write_text(content, encoding="utf-8")
    config_kt = Path(kiosk_project) / "app/src/main/java/id/siab1/kiosk/AppConfig.kt"
    if config_kt.is_file():
        kt = config_kt.read_text(encoding="utf-8")
        kt = re.sub(
            r'const val buildToken: String = "[^"]+"',
            f'const val buildToken: String = "{build_token}"',
            kt,
            count=1,
        )
        kt = re.sub(
            r'const val appName: String = "[^"]+"',
            f'const val appName: String = "{safe_name}"',
            kt,
            count=1,
        )
        config_kt.write_text(kt, encoding="utf-8")
    strings = Path(kiosk_project) / "app/src/main/res/values/strings.xml"
    if strings.is_file():
        xml = strings.read_text(encoding="utf-8")
        xml = re.sub(
            r'<string name="app_name">[^<]*</string>',
            f'<string name="app_name">{safe_name}</string>',
            xml,
            count=1,
        )
        strings.write_text(xml, encoding="utf-8")
