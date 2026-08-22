"""Project context discovery for APK builder tooling."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectContext:
    project_root: Path
    flutter_project: Path
    config_dart_path: Path


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / "flutter_client_code" / "lib" / "config.dart").exists():
            return candidate
        if (candidate / ".git").exists() and (candidate / "flutter_client_code").exists():
            return candidate
    return current.parent if current.name == "tools" else current


def detect_project_context(script_file: str | Path) -> ProjectContext:
    """Resolve repo root and Flutter project paths from a script path."""
    root = _find_repo_root(Path(script_file))
    flutter_project = root / "flutter_client_code"
    config_dart_path = flutter_project / "lib" / "config.dart"
    return ProjectContext(
        project_root=root,
        flutter_project=flutter_project,
        config_dart_path=config_dart_path,
    )
