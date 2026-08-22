"""Validation helpers for APK builder tooling."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse


_PACKAGE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+$")
_SHA256_RE = re.compile(r"^[A-Fa-f0-9]{64}$")


def normalize_server_url(raw_url: str, *, use_https: bool = True) -> str:
    """Normalize a server root URL and keep a trailing slash."""
    value = (raw_url or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = f"{'https' if use_https else 'http'}://{value}"
    parsed = urlparse(value)
    scheme = "https" if use_https else (parsed.scheme or "http")
    netloc = parsed.netloc or parsed.path
    path = parsed.path if parsed.netloc else ""
    normalized = urlunparse((scheme, netloc, path.rstrip("/") + "/", "", "", ""))
    return normalized


def is_valid_package_name(package_name: str) -> bool:
    return bool(_PACKAGE_RE.match((package_name or "").strip()))


def is_valid_sha256(value: str) -> bool:
    return bool(_SHA256_RE.match((value or "").replace(":", "").strip()))


def load_properties_file(path: Path) -> dict[str, str]:
    props: dict[str, str] = {}
    path = Path(path)
    if not path.exists():
        return props
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        props[key.strip()] = value.strip()
    return props


def save_properties_file(path: Path, props: dict[str, str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(f"{key}={value}" for key, value in sorted(props.items()))
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")


def parse_pubspec_version(version_value: str) -> tuple[str, str]:
    value = (version_value or "").strip()
    if "+" in value:
        name, code = value.split("+", 1)
        return name.strip(), code.strip()
    return value, "1"


def validate_version_fields(version_name: str, version_code: str) -> tuple[bool, str | None]:
    name = (version_name or "").strip()
    code = (version_code or "").strip()
    if not re.match(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$", name):
        return False, "Version name harus format semver, contoh: 1.0.2"
    if not code.isdigit() or int(code) <= 0:
        return False, "Version code harus angka positif."
    return True, None


def find_main_activity_file(flutter_project: Path) -> Path | None:
    root = Path(flutter_project) / "android" / "app" / "src" / "main"
    if not root.exists():
        return None
    matches = list(root.glob("kotlin/**/MainActivity.*")) + list(root.glob("java/**/MainActivity.*"))
    if not matches:
        return None
    return matches[0]
