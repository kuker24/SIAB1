"""
Session recovery policies for students who are disconnected ("terpental").
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, TYPE_CHECKING

from app.core.violation_metadata import AUTO_SUBMIT_VIOLATION_THRESHOLD

if TYPE_CHECKING:
    from app.models.session import ExamLog, ExamSession
else:
    ExamLog = Any
    ExamSession = Any


RECOVERY_CATEGORY_NETWORK = "network_issue"
RECOVERY_CATEGORY_CHEATING = "cheating_detected"
RECOVERY_CATEGORY_ADMIN = "admin_decision"
RECOVERY_CATEGORY_SUBMITTED = "session_submitted"
RECOVERY_CATEGORY_COMPLETED = "session_completed"
RECOVERY_CATEGORY_UNKNOWN = "unknown"


def _event_type(log: ExamLog) -> str:
    return str(getattr(log, "event_type", "") or "").strip().upper()


def _event_data(log: ExamLog) -> Dict[str, Any]:
    payload = getattr(log, "event_data", None)
    if isinstance(payload, dict):
        return payload
    return {}


def _contains_admin_decision(logs: Iterable[ExamLog]) -> bool:
    admin_events = {
        "FORCE_SUBMIT_BY_TEACHER",
        "SESSION_TERMINATED",
        "ADMIN_KICK_STUDENT",
        "SESSION_FORCE_KICK",
    }
    for log in logs:
        if _event_type(log) in admin_events:
            return True
    return False


def _contains_cheating_submit(logs: Iterable[ExamLog]) -> bool:
    for log in logs:
        event_type = _event_type(log)
        payload = _event_data(log)
        if event_type in {"EXAM_SUBMIT", "EXAM_SUBMITTED"} and bool(payload.get("force_submit")):
            return True
        if event_type == "AUTO_SUBMIT_VIOLATION":
            return True
    return False


def evaluate_session_recovery(
    session: ExamSession,
    logs: Optional[Iterable[ExamLog]] = None,
) -> Dict[str, Any]:
    """
    Determine whether a session can continue after disconnection.

    Rules:
    - network_issue -> allow continue
    - cheating_detected -> block
    - admin_decision -> block
    - submitted/completed -> block
    """
    logs_list = list(logs or [])
    status = str(getattr(session, "status", "") or "").lower()
    terminated_by_admin = bool(getattr(session, "terminated_by_admin", False))
    violation_count = int(getattr(session, "violation_count", 0) or 0)

    if status in {"submitted", "completed"}:
        if _contains_admin_decision(logs_list):
            return {
                "category": RECOVERY_CATEGORY_ADMIN,
                "allow_continue": False,
                "message": "Sesi dikumpulkan/dihentikan oleh pengawas. Siswa tidak boleh melanjutkan.",
            }
        if _contains_cheating_submit(logs_list) or violation_count >= AUTO_SUBMIT_VIOLATION_THRESHOLD:
            return {
                "category": RECOVERY_CATEGORY_CHEATING,
                "allow_continue": False,
                "message": "Sesi dihentikan karena pelanggaran. Siswa tidak boleh melanjutkan.",
            }
        return {
            "category": RECOVERY_CATEGORY_SUBMITTED if status == "submitted" else RECOVERY_CATEGORY_COMPLETED,
            "allow_continue": False,
            "message": "Sesi sudah selesai/dikumpulkan.",
        }

    if status in {"terminated", "kicked"}:
        if terminated_by_admin or _contains_admin_decision(logs_list):
            return {
                "category": RECOVERY_CATEGORY_ADMIN,
                "allow_continue": False,
                "message": "Sesi dihentikan oleh pengawas/admin. Siswa tidak boleh melanjutkan.",
            }
        if _contains_cheating_submit(logs_list):
            return {
                "category": RECOVERY_CATEGORY_CHEATING,
                "allow_continue": False,
                "message": "Sesi dihentikan karena pelanggaran. Siswa tidak boleh melanjutkan.",
            }
        return {
            "category": RECOVERY_CATEGORY_NETWORK,
            "allow_continue": True,
            "message": "Sesi dihentikan karena kendala koneksi. Siswa boleh melanjutkan dari jawaban terakhir.",
        }

    if status in {"in_progress", "active", "paused"}:
        return {
            "category": RECOVERY_CATEGORY_NETWORK,
            "allow_continue": True,
            "message": "Sesi aktif dan dapat dilanjutkan.",
        }

    return {
        "category": RECOVERY_CATEGORY_UNKNOWN,
        "allow_continue": False,
        "message": "Sesi tidak dikenali. Perlu pemeriksaan admin.",
    }
