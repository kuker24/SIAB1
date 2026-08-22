"""
Scheduled non-destructive DR drill task.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Dict

from celery import shared_task

from app.config import settings

logger = logging.getLogger(__name__)


@shared_task(name="app.tasks.dr_drill.run_disaster_recovery_drill")
def run_disaster_recovery_drill() -> Dict[str, object]:
    if not settings.dr_drill_enabled:
        return {"status": "disabled", "reason": "DR_DRILL_ENABLED=false"}

    script_path = Path("/app/scripts/drill_disaster_recovery.sh")
    if not script_path.exists():
        return {"status": "missing_script", "path": str(script_path)}

    timeout_seconds = max(60, int(settings.dr_drill_timeout_seconds or 1800))
    try:
        completed = subprocess.run(
            [str(script_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        stdout = (completed.stdout or "").strip().splitlines()
        summary_tail = stdout[-8:] if stdout else []
        logger.info("DR drill success: %s", " | ".join(summary_tail))
        return {
            "status": "ok",
            "timeout_seconds": timeout_seconds,
            "summary_tail": summary_tail,
        }
    except subprocess.TimeoutExpired:
        logger.error("DR drill timed out after %ss", timeout_seconds)
        return {
            "status": "timeout",
            "timeout_seconds": timeout_seconds,
        }
    except subprocess.CalledProcessError as exc:
        logger.error("DR drill failed: %s", exc, exc_info=True)
        stderr_lines = (exc.stderr or "").strip().splitlines()
        return {
            "status": "error",
            "returncode": exc.returncode,
            "stderr_tail": stderr_lines[-10:],
        }
