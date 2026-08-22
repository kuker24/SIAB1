from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {
    ".conf",
    ".csv",
    ".dart",
    ".example",
    ".go",
    ".gradle",
    ".html",
    ".json",
    ".kt",
    ".kts",
    ".md",
    ".properties",
    ".py",
    ".sh",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
BANNED_IDENTITY_PATTERNS = {
    "legacy product name": re.compile(r"ujian[ _-]?online", re.IGNORECASE),
    "legacy database name": re.compile(r"\bexam_system\b", re.IGNORECASE),
    "legacy project label": re.compile(r"\b(?:jules|up5)\b", re.IGNORECASE),
    "legacy production domain": re.compile(r"man1rokanhulu\.cloud", re.IGNORECASE),
    "legacy production address": re.compile(r"103\.175\.218\.56"),
    "legacy Android package": re.compile(r"com\.(?:school\.examapp|example\.sxb_client)"),
}


def _repository_text_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        ROOT / relative
        for relative in result.stdout.splitlines()
        if (ROOT / relative).exists() and (ROOT / relative).suffix.lower() in TEXT_SUFFIXES
    ]


def test_active_repository_uses_only_siab1_identity() -> None:
    findings: list[str] = []
    for path in _repository_text_files():
        if path == Path(__file__).resolve():
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        for label, pattern in BANNED_IDENTITY_PATTERNS.items():
            if pattern.search(source):
                findings.append(f"{path.relative_to(ROOT)}: {label}")

    assert findings == []


def test_runtime_defaults_use_siab1_identifiers() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())
    env_example = (ROOT / ".env.example").read_text()
    kotlin_build = (ROOT / "android-kiosk/app/build.gradle.kts").read_text()
    flutter_build = (ROOT / "flutter_client_code/android/app/build.gradle").read_text()

    assert compose["services"]["api"]["image"] == "siab1-api"
    assert compose["name"] == "siab1"
    assert "POSTGRES_DB=siab1" in set(compose["services"]["db"]["environment"])
    assert "POSTGRES_DB=siab1" in env_example
    assert 'applicationId = "id.siab1.kiosk"' in kotlin_build
    assert 'applicationId "id.siab1.flutter"' in flutter_build


def test_obsolete_files_are_removed() -> None:
    obsolete = (
        "config/security.py",
        "static/css/admin-styles.css",
        "templates/exam/questions.html",
        "flutter_client_code/android_src/MainActivity.kt",
        "flutter_client_code/windows_src/windows_kiosk_snippet.cpp",
        "install.sh",
        "uninstall.sh",
        "option.sh",
    )
    assert all(not (ROOT / relative).exists() for relative in obsolete)


def test_local_markdown_links_resolve() -> None:
    missing: list[str] = []
    link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    for path in _repository_text_files():
        if path.suffix.lower() != ".md":
            continue
        for target in link_pattern.findall(path.read_text(encoding="utf-8")):
            clean_target = target.split("#", 1)[0].strip()
            if not clean_target or "://" in clean_target or clean_target.startswith("mailto:"):
                continue
            resolved = (path.parent / clean_target).resolve()
            if not resolved.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {target}")

    assert missing == []
