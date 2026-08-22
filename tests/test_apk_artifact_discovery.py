import os
from pathlib import Path

from app.api import apk


def test_iter_artifacts_includes_versioned_apk_subdirectories(monkeypatch, tmp_path: Path) -> None:
    build_dir = tmp_path / "apk_builds"
    version_dir = build_dir / "1.0.0.2"
    version_dir.mkdir(parents=True)
    legacy_dir = tmp_path / "static" / "apk"
    legacy_dir.mkdir(parents=True)

    old_top_level = build_dir / "old.apk"
    current_nested = version_dir / "current.apk"
    old_top_level.write_bytes(b"old")
    current_nested.write_bytes(b"current")

    os.utime(old_top_level, (1000, 1000))
    os.utime(current_nested, (2000, 2000))

    monkeypatch.setattr(apk, "APK_BUILD_DIR", build_dir)
    monkeypatch.setattr(apk, "LEGACY_APK_DIR", legacy_dir)

    artifacts = apk._iter_artifacts()
    artifact_names = [item.name for item in artifacts]

    assert "current.apk" in artifact_names
    assert "old.apk" in artifact_names
    assert artifact_names[0] == "current.apk"
