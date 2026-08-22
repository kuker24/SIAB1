from pathlib import Path

from tools.apk_builder_core.environment import build_tool_env, find_flutter


def test_find_flutter_uses_valid_local_properties_sdk(tmp_path: Path) -> None:
    flutter_project = tmp_path / "flutter_client_code"
    android_dir = flutter_project / "android"
    fake_sdk = tmp_path / "flutter_sdk"
    flutter_bin = fake_sdk / "bin" / "flutter"
    android_dir.mkdir(parents=True)
    flutter_bin.parent.mkdir(parents=True)
    flutter_bin.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    flutter_bin.chmod(0o755)
    (android_dir / "local.properties").write_text(
        f"flutter.sdk={fake_sdk}\n",
        encoding="utf-8",
    )

    assert find_flutter(flutter_project=flutter_project) == str(flutter_bin)


def test_find_flutter_ignores_stale_local_properties_and_uses_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    flutter_project = tmp_path / "flutter_client_code"
    android_dir = flutter_project / "android"
    path_dir = tmp_path / "bin"
    flutter_bin = path_dir / "flutter"
    android_dir.mkdir(parents=True)
    path_dir.mkdir(parents=True)
    flutter_bin.write_text("#!/usr/bin/env sh\n", encoding="utf-8")
    flutter_bin.chmod(0o755)
    (android_dir / "local.properties").write_text(
        "flutter.sdk=/missing/flutter/sdk\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", str(path_dir))

    assert find_flutter(flutter_project=flutter_project) == str(flutter_bin)


def test_build_tool_env_adds_flutter_to_path(tmp_path: Path) -> None:
    flutter_bin = tmp_path / "flutter" / "bin" / "flutter"
    flutter_bin.parent.mkdir(parents=True)
    flutter_bin.write_text("#!/usr/bin/env sh\n", encoding="utf-8")

    env = build_tool_env(None, None, str(flutter_bin))

    assert str(flutter_bin.parent) in env["PATH"]
    assert env["FLUTTER_ROOT"] == str(flutter_bin.parent.parent)
