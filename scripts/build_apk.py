"""
Build script for Android artifacts (APK/AAB).

Usage:
    python scripts/build_apk.py <build_id> <app_name> [icon_path] [build_mode]

build_mode:
    - universal_apk (default)
    - split_apk
    - app_bundle
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLUTTER_PROJECT = PROJECT_ROOT / "flutter_client_code"
ANDROID_RES = FLUTTER_PROJECT / "android" / "app" / "src" / "main" / "res"
APK_ARCHIVE_DIR = PROJECT_ROOT / "apk_builds"
STATIC_APK_DIR = PROJECT_ROOT / "static" / "apk" / "builds"


def run_cmd(cmd: list[str], cwd: Path):
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def update_app_name(app_name: str):
    """Update app metadata in pubspec.yaml."""
    pubspec_path = FLUTTER_PROJECT / "pubspec.yaml"
    with pubspec_path.open("r", encoding="utf-8") as f:
        pubspec = yaml.safe_load(f)

    safe_name = "".join(ch for ch in app_name.lower().replace(" ", "_") if ch.isalnum() or ch == "_")
    pubspec["name"] = safe_name or "siab1_client"
    pubspec["description"] = f"{app_name} - Secure Exam Browser"

    with pubspec_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(pubspec, f, sort_keys=False, default_flow_style=False, allow_unicode=True)

    print(f"✓ Updated app metadata: name={pubspec['name']}")


def update_app_icon(icon_path: str):
    """Replace Android launcher icons."""
    if not icon_path or not Path(icon_path).exists():
        print("⚠ No custom icon provided, using existing launcher icons")
        return

    sizes = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }

    img = Image.open(icon_path).convert("RGBA")
    resample = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS

    for folder, size in sizes.items():
        out_dir = ANDROID_RES / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        resized = img.resize((size, size), resample)
        resized.save(out_dir / "ic_launcher.png")

    print(f"✓ Updated launcher icons ({len(sizes)} sizes)")


def build_artifact(build_mode: str):
    """Run Flutter build based on selected mode."""
    print("\n🔨 Running Flutter build...")
    run_cmd(["flutter", "pub", "get"], cwd=FLUTTER_PROJECT)

    if build_mode == "app_bundle":
        run_cmd(["flutter", "build", "appbundle", "--release"], cwd=FLUTTER_PROJECT)
        out_dir = FLUTTER_PROJECT / "build" / "app" / "outputs" / "bundle" / "release"
        return sorted(out_dir.glob("*.aab"))

    if build_mode == "split_apk":
        run_cmd(["flutter", "build", "apk", "--release", "--split-per-abi"], cwd=FLUTTER_PROJECT)
    else:
        run_cmd(["flutter", "build", "apk", "--release"], cwd=FLUTTER_PROJECT)

    out_dir = FLUTTER_PROJECT / "build" / "app" / "outputs" / "apk" / "release"
    return sorted(out_dir.glob("*.apk"))


def copy_artifacts(artifacts: list[Path], build_id: int, app_name: str):
    if not artifacts:
        raise FileNotFoundError("No build artifacts generated.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(ch for ch in app_name.lower().replace(" ", "_") if ch.isalnum() or ch == "_")
    safe_name = safe_name or "siab1_client"

    archive_dir = APK_ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    static_dir = STATIC_APK_DIR / str(build_id)
    static_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for artifact in artifacts:
        arch = "universal"
        if "arm64-v8a" in artifact.name:
            arch = "arm64"
        elif "armeabi-v7a" in artifact.name:
            arch = "armv7"
        elif "x86_64" in artifact.name:
            arch = "x86_64"
        elif "x86" in artifact.name:
            arch = "x86"

        suffix = artifact.suffix.lower()
        filename = f"{safe_name}_{timestamp}{suffix}" if arch == "universal" else f"{safe_name}_{arch}_{timestamp}{suffix}"
        archive_path = archive_dir / filename
        static_path = static_dir / filename

        shutil.copy2(artifact, archive_path)
        shutil.copy2(artifact, static_path)
        copied.append(archive_path)

    print(f"✓ Copied {len(copied)} artifacts to {archive_dir} and {static_dir}")
    return copied


def main(build_id: int, app_name: str, icon_path: str = "", build_mode: str = "universal_apk"):
    print("\n" + "=" * 68)
    print("APK/AAB Build Automation")
    print("=" * 68)
    print(f"Build ID   : {build_id}")
    print(f"App Name   : {app_name}")
    print(f"Icon Path  : {icon_path or '-'}")
    print(f"Build Mode : {build_mode}")
    print("=" * 68 + "\n")

    if build_mode not in {"universal_apk", "split_apk", "app_bundle"}:
        raise ValueError("Invalid build mode. Use: universal_apk | split_apk | app_bundle")

    update_app_name(app_name)
    if icon_path:
        update_app_icon(icon_path)

    artifacts = build_artifact(build_mode)
    copied = copy_artifacts(artifacts, build_id, app_name)

    total_size = sum(path.stat().st_size for path in copied)
    print("\n✅ BUILD COMPLETE")
    for path in copied:
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  - {path} ({size_mb:.2f} MB)")
    print(f"Total size: {total_size / (1024 * 1024):.2f} MB")

    return {
        "status": "success",
        "artifacts": [str(p) for p in copied],
        "total_size_bytes": total_size,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/build_apk.py <build_id> <app_name> [icon_path] [build_mode]")
        sys.exit(1)

    build_id_arg = int(sys.argv[1])
    app_name_arg = sys.argv[2]
    icon_path_arg = sys.argv[3] if len(sys.argv) > 3 else ""
    build_mode_arg = sys.argv[4] if len(sys.argv) > 4 else "universal_apk"

    result = main(build_id_arg, app_name_arg, icon_path_arg, build_mode_arg)
    print(f"\nResult: {result}")
