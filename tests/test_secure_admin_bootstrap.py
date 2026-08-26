from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
SCRIPT = ROOT / "scripts" / "bootstrap_admin.py"


def _run_bootstrap(password: str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("SIAB1_BOOTSTRAP_ADMIN_PASSWORD", None)
    if password is not None:
        env["SIAB1_BOOTSTRAP_ADMIN_PASSWORD"] = password
    return subprocess.run(
        [str(PYTHON), str(SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_admin_bootstrap_requires_explicit_password() -> None:
    result = _run_bootstrap(None)

    assert result.returncode == 2
    assert "SIAB1_BOOTSTRAP_ADMIN_PASSWORD is required" in result.stderr


def test_admin_bootstrap_rejects_weak_password_before_database_access() -> None:
    result = _run_bootstrap("too-short")

    assert result.returncode == 2
    assert "at least 12 characters" in result.stderr
