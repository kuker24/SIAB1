"""Environment helpers for APK builder tooling."""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Callable, Mapping


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path and path.exists():
            return path
    return None


def find_jdk(project_root: Path | None = None) -> str | None:
    """Best-effort JDK discovery without mutating the environment."""
    env_java_home = os.environ.get("JAVA_HOME")
    candidates: list[Path] = []
    if env_java_home:
        candidates.append(Path(env_java_home))
    if project_root:
        candidates.extend([
            Path(project_root) / "jdk",
            Path(project_root) / "java",
        ])
    if platform.system().lower().startswith("win"):
        candidates.extend(Path("C:/Program Files/Java").glob("jdk*"))
        candidates.extend(Path("C:/Program Files/Eclipse Adoptium").glob("jdk*"))
    else:
        candidates.extend(Path("/usr/lib/jvm").glob("java-*"))
        candidates.extend(Path("/usr/lib/jvm").glob("jdk-*"))
    found = _first_existing(candidates)
    return str(found) if found else None


def find_android_sdk() -> str | None:
    """Best-effort Android SDK discovery."""
    for key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(key)
        if value and Path(value).exists():
            return value
    home = Path.home()
    candidates = [
        home / "Android" / "Sdk",
        home / "Library" / "Android" / "sdk",
        Path("/opt/android-sdk"),
    ]
    found = _first_existing(candidates)
    return str(found) if found else None


def _flutter_executable_from_sdk(sdk_dir: str | Path | None) -> Path | None:
    if not sdk_dir:
        return None
    exe = "flutter.bat" if platform.system().lower().startswith("win") else "flutter"
    candidate = Path(sdk_dir) / "bin" / exe
    return candidate if candidate.exists() else None


def _read_flutter_sdk_from_local_properties(flutter_project: Path | None) -> str | None:
    if not flutter_project:
        return None
    local_props = Path(flutter_project) / "android" / "local.properties"
    if not local_props.exists():
        return None
    try:
        for raw_line in local_props.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "flutter.sdk" and value.strip():
                return value.strip()
    except OSError:
        return None
    return None


def find_flutter(
    flutter_project: Path | None = None,
    project_root: Path | None = None,
) -> str | None:
    """Best-effort Flutter executable discovery for GUI/CLI builds.

    Discovery order is intentionally local-first so GUI builds keep working even
    when Flutter is not exported in the desktop shell PATH.
    """
    candidates: list[Path] = []

    # Explicit executable override.
    env_flutter_bin = os.environ.get("FLUTTER_BIN")
    if env_flutter_bin:
        candidates.append(Path(env_flutter_bin))

    # SDK roots from local.properties/env/common install folders.
    sdk_roots: list[str | Path] = []
    local_sdk = _read_flutter_sdk_from_local_properties(flutter_project)
    if local_sdk:
        sdk_roots.append(local_sdk)
    for key in ("FLUTTER_ROOT", "FLUTTER_HOME"):
        value = os.environ.get(key)
        if value:
            sdk_roots.append(value)
    if project_root:
        sdk_roots.extend([
            Path(project_root) / "flutter",
            Path(project_root) / "flutter_sdk",
            Path(project_root) / ".flutter_sdk",
        ])
    home = Path.home()
    sdk_roots.extend([
        home / ".cache" / "flutter_sdk",
        home / "flutter",
        home / "development" / "flutter",
        Path("/opt/flutter"),
    ])

    for sdk_root in sdk_roots:
        executable = _flutter_executable_from_sdk(sdk_root)
        if executable:
            candidates.append(executable)

    path_flutter = shutil.which("flutter")
    if path_flutter:
        candidates.append(Path(path_flutter))

    found = _first_existing(candidates)
    return str(found) if found else None


def get_total_ram_mb() -> int:
    """Return total RAM in MB using only stdlib/best-effort probes."""
    try:
        if hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return int(pages * page_size / (1024 * 1024))
    except Exception:
        pass
    return 4096


def recommend_gradle_memory(force_high: bool = False) -> tuple[str, str]:
    """Recommend Gradle JVM args and heap size label."""
    total_mb = get_total_ram_mb()
    if force_high or total_mb >= 12000:
        return "-Xmx4096m -Dfile.encoding=UTF-8", "4096m"
    if total_mb >= 8000:
        return "-Xmx3072m -Dfile.encoding=UTF-8", "3072m"
    return "-Xmx2048m -Dfile.encoding=UTF-8", "2048m"


def build_tool_env(
    jdk_path: str | None,
    android_sdk: str | None,
    flutter_bin: str | None = None,
) -> dict[str, str]:
    """Return environment for subprocess-based Flutter/Android build commands."""
    env = dict(os.environ)
    path_parts: list[str] = []
    if jdk_path:
        env["JAVA_HOME"] = jdk_path
        path_parts.append(str(Path(jdk_path) / "bin"))
    if android_sdk:
        env["ANDROID_HOME"] = android_sdk
        env["ANDROID_SDK_ROOT"] = android_sdk
        path_parts.extend([
            str(Path(android_sdk) / "platform-tools"),
            str(Path(android_sdk) / "cmdline-tools" / "latest" / "bin"),
        ])
    if flutter_bin:
        flutter_path = Path(flutter_bin)
        path_parts.append(str(flutter_path.parent))
        if flutter_path.parent.name == "bin":
            env["FLUTTER_ROOT"] = str(flutter_path.parent.parent)
    if path_parts:
        env["PATH"] = os.pathsep.join(path_parts + [env.get("PATH", "")])
    return env


def ensure_gradle_memory_config(
    *,
    flutter_project: Path | None = None,
    gradle_properties: Path | None = None,
    env: Mapping[str, str] | None = None,
    log: Callable[[str], None] | None = None,
    force_high: bool = False,
) -> None:
    """Ensure gradle.properties has a safe org.gradle.jvmargs value."""
    if gradle_properties is None:
        if flutter_project is None:
            raise ValueError("flutter_project or gradle_properties is required")
        gradle_properties = Path(flutter_project) / "android" / "gradle.properties"
    gradle_props = Path(gradle_properties)
    gradle_props.parent.mkdir(parents=True, exist_ok=True)
    jvmargs, heap_label = recommend_gradle_memory(force_high=force_high)
    line = f"org.gradle.jvmargs={jvmargs}"
    existing = gradle_props.read_text(encoding="utf-8") if gradle_props.exists() else ""
    lines = []
    replaced = False
    for raw in existing.splitlines():
        if raw.startswith("org.gradle.jvmargs="):
            lines.append(line)
            replaced = True
        else:
            lines.append(raw)
    if not replaced:
        lines.append(line)
    gradle_props.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    if log:
        log(f"Gradle memory configured: {heap_label}")


def resolve_keytool(jdk_path: str | None) -> str | None:
    exe = "keytool.exe" if platform.system().lower().startswith("win") else "keytool"
    if jdk_path:
        candidate = Path(jdk_path) / "bin" / exe
        if candidate.exists():
            return str(candidate)
    return shutil.which("keytool")


def resolve_apksigner(android_sdk: str | None) -> str | None:
    exe = "apksigner.bat" if platform.system().lower().startswith("win") else "apksigner"
    if android_sdk:
        build_tools = Path(android_sdk) / "build-tools"
        if build_tools.exists():
            versions = sorted([p for p in build_tools.iterdir() if p.is_dir()], reverse=True)
            for version in versions:
                candidate = version / exe
                if candidate.exists():
                    return str(candidate)
    return shutil.which("apksigner")
