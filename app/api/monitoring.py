"""
Monitoring API endpoints for violation tracking and live exam statistics.
Provides real-time monitoring capabilities for admins and teachers.
"""
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.feature_flags import require_feature_enabled
from app.database import get_db_read, get_db_write
from app.models.user import User
from app.models.exam import Exam
from app.models.question import Question
from app.models.session import Answer, ExamSession, ExamLog
from app.api.monitoring_restart import (
    _build_full_restart_services,
    _delete_redis_keys_by_patterns,
    _ensure_full_restart_available,
    _execute_full_restart,
    _restart_backend_status,
)
from app.api.monitoring_schemas import (
    AutoIntelligenceControlUpdate,
    AutoIntelligenceRunRequest,
    AutoRestartRunRequest,
    AutoRestartScheduleUpdate,
    DegradeModeUpdate,
    KickStudentRequest,
    LiveExamStats,
    RecoveryCandidate,
    RecoveryCandidatesResponse,
    ResourceModeUpdate,
    RestartSystemRequest,
    SessionOverrideResetRequest,
    SessionResetRequest,
    SessionStatus,
    ViolationStats,
)
from app.core.security import (
    get_current_exam_monitor,
    get_current_active_admin,
    get_current_user,
    is_pengawas_user,
    is_teacher_scope_restricted,
)
from app.core.metrics_collector import metrics_collector
from app.core.ops_summary import get_ops_summary, invalidate_ops_summary_cache
from app.core.redis_pubsub import get_redis
from app.core.degrade_mode import (
    get_runtime_policy,
    get_degrade_mode_state,
    set_degrade_mode,
    get_resource_mode_state,
    set_resource_mode,
    get_resource_mode_catalog,
)
from app.core.auto_intelligence import (
    get_auto_intelligence_status,
    run_auto_intelligence_tick,
    update_auto_intelligence_controls,
)
from app.core.auto_restart import (
    get_auto_restart_schedule,
    get_auto_restart_status,
    set_auto_restart_schedule,
    run_auto_restart_scheduler_tick,
)
from app.core.restart_safe import (
    RESTART_SAFE_EXEC_LOCK_KEY,
    RESTART_SAFE_FULL_COOLDOWN_SECONDS,
    acquire_restart_safe_exec_lock as _acquire_restart_safe_exec_lock,
    build_restart_safe_cooldown_state as _build_restart_safe_cooldown_state,
    get_restart_safe_last_exec as _get_restart_safe_last_exec,
    parse_iso_timestamp as _parse_iso_timestamp,
    release_restart_safe_exec_lock as _release_restart_safe_exec_lock,
    set_restart_safe_last_exec as _set_restart_safe_last_exec,
)
from app.core.runtime_telemetry import get_runtime_snapshot
from app.core.monitoring_delta import read_monitoring_delta
from app.core.exam_runtime_state import (
    get_answered_counts_bulk,
    get_runtime_snapshots_bulk,
)
from app.core.violation_metadata import VIOLATION_TYPE_METADATA
from app.core.violation_scoring import VIOLATION_DISABLED_EVENT_TYPES
from app.core.violations_dashboard import (
    _ensure_aware_datetime,
    _build_violations_aggregate_payload,
    _build_violations_dashboard_payload,
    _build_violations_export_filename,
    _build_violations_query,
    _build_violations_summary_payload,
    _coerce_violations_date_range,
    _resolve_selected_exam_title,
)
from app.core.session_recovery import evaluate_session_recovery

# Compatibility marker for guard tests and audit readability:
# counted violation query excludes disabled events via notin_(disabled_types)
# where disabled_types originates from VIOLATION_DISABLED_EVENT_TYPES.
#
# Restart-safe constants remain visible at API module level:
# RESTART_SAFE_EXEC_LOCK_KEY, RESTART_SAFE_FULL_COOLDOWN_SECONDS

router = APIRouter(prefix="/api/monitoring", tags=["Monitoring"])
logger = logging.getLogger(__name__)

ACTIVE_EXAMS_CACHE_TTL_SECONDS = 3.0
_active_exams_cache: Dict[str, Dict[str, Any]] = {}


def _active_exams_cache_key(current_user: User) -> str:
    if is_pengawas_user(current_user):
        return "pengawas:all"
    if current_user.role == "teacher":
        return f"teacher:{current_user.id}"
    return "admin:all"


def _get_active_exams_cached(cache_key: str) -> Optional[Dict[str, Any]]:
    entry = _active_exams_cache.get(cache_key)
    if not entry:
        return None

    cached_at = float(entry.get("cached_at", 0.0) or 0.0)
    if (time.monotonic() - cached_at) > ACTIVE_EXAMS_CACHE_TTL_SECONDS:
        _active_exams_cache.pop(cache_key, None)
        return None

    payload = entry.get("payload")
    if isinstance(payload, dict):
        return payload
    return None


def _set_active_exams_cache(cache_key: str, payload: Dict[str, Any]) -> None:
    _active_exams_cache[cache_key] = {
        "cached_at": time.monotonic(),
        "payload": payload,
    }


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


async def _get_bulk_session_activity(exam_id: int, user_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """
    Fetch heartbeat cache in bulk to avoid N+1 Redis round-trips per session row.
    """
    if not user_ids:
        return {}
    activity_map: Dict[int, Dict[str, Any]] = {}
    unique_user_ids = list(dict.fromkeys(user_ids))
    keys = [f"exam_activity:{exam_id}:{uid}" for uid in unique_user_ids]
    try:
        redis = await get_redis()
        raw_values = await redis.mget(keys)
    except Exception as exc:
        logger.warning("Bulk activity fetch failed for exam=%s: %s", exam_id, exc)
        return {}

    for uid, raw in zip(unique_user_ids, raw_values):
        if raw is None:
            continue
        try:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            payload = json.loads(raw)
            if isinstance(payload, dict):
                activity_map[uid] = payload
        except Exception:
            continue
    return activity_map


async def _get_answered_count_map(
    db: AsyncSession,
    session_ids: List[int],
) -> Dict[int, int]:
    """
    Resolve answered-count map with Redis-first strategy and DB fallback.
    """
    if not session_ids:
        return {}

    normalized_ids = [int(sid) for sid in session_ids if sid is not None]
    answered_map: Dict[int, int] = {}

    # Layer 1: runtime snapshots (exam_session:{id}) when fresh.
    try:
        runtime_snapshots = await get_runtime_snapshots_bulk(normalized_ids)
    except Exception as exc:
        logger.debug("Runtime snapshot bulk read failed: %s", str(exc))
        runtime_snapshots = {}

    unresolved_ids: List[int] = []
    for sid in normalized_ids:
        snapshot = runtime_snapshots.get(sid) or {}
        is_stale = bool(snapshot.get("answered_count_stale"))
        raw_count = _safe_int(snapshot.get("answered_count"))
        if not is_stale and raw_count is not None and raw_count >= 0:
            answered_map[sid] = int(raw_count)
        else:
            unresolved_ids.append(sid)

    # Layer 2: Redis set counters (exam_answered_questions:{id}).
    if unresolved_ids:
        try:
            set_counts = await get_answered_counts_bulk(unresolved_ids)
        except Exception as exc:
            logger.debug("Answered-count set bulk read failed: %s", str(exc))
            set_counts = {}
        for sid, count in set_counts.items():
            answered_map[int(sid)] = max(0, int(count))
        unresolved_ids = [sid for sid in unresolved_ids if sid not in answered_map]

    # Layer 3: DB fallback only for unresolved sessions.
    if unresolved_ids:
        answered_counts_result = await db.execute(
            select(
                Answer.session_id,
                func.count(Answer.id).label("answered_count"),
            )
            .where(Answer.session_id.in_(unresolved_ids))
            .group_by(Answer.session_id)
        )
        for session_id, answered_count in answered_counts_result.fetchall():
            answered_map[int(session_id)] = int(answered_count or 0)
        # Sessions with no answers should return 0.
        for sid in unresolved_ids:
            answered_map.setdefault(int(sid), 0)

    return answered_map


RECOVERY_TERMINAL_STATUSES = {"submitted", "completed", "terminated", "kicked", "abandoned"}
RECOVERY_RELEVANT_EVENTS = {
    "EXAM_SUBMIT",
    "EXAM_SUBMITTED",
    "AUTO_SUBMIT_VIOLATION",
    "FORCE_SUBMIT_BY_TEACHER",
    "SESSION_TERMINATED",
    "SESSION_FORCE_KICK",
    "ADMIN_KICK_STUDENT",
    "SESSION_MANUAL_RESET",
    "SESSION_RESET_BLOCKED",
    "SESSION_REOPENED_BY_ADMIN",
    "SESSION_ADMIN_OVERRIDE_REOPEN",
}
RECOVERY_REASON_LABELS = {
    "network_issue": "Gangguan jaringan / koneksi",
    "cheating_detected": "Pelanggaran / auto-submit",
    "admin_decision": "Keputusan pengawas/admin",
    "user_submit": "Submit normal oleh siswa",
    "unknown": "Perlu verifikasi admin",
}
RECOVERY_REASON_SORT = {
    "network_issue": 0,
    "unknown": 1,
    "cheating_detected": 2,
    "admin_decision": 3,
    "user_submit": 4,
}


def _log_event_type(log: ExamLog) -> str:
    return str(getattr(log, "event_type", "") or "").strip().upper()


def _log_event_data(log: ExamLog) -> Dict[str, Any]:
    payload = getattr(log, "event_data", None)
    if isinstance(payload, dict):
        return payload
    return {}


def _derive_submit_mode(logs: List[ExamLog]) -> str:
    for log in logs:
        event_type = _log_event_type(log)
        payload = _log_event_data(log)
        if event_type == "AUTO_SUBMIT_VIOLATION":
            return "auto_violation"
        if event_type in {"EXAM_SUBMIT", "EXAM_SUBMITTED"}:
            if bool(payload.get("force_submit")):
                return "force_submit"
            return "user_submit"
        if event_type in {"FORCE_SUBMIT_BY_TEACHER"}:
            return "admin_force_submit"
    return "unknown"


def _derive_reason_bucket(status: str, recovery_category: str, submit_mode: str) -> str:
    normalized_status = str(status or "").lower()
    normalized_category = str(recovery_category or "").strip().lower()
    normalized_submit_mode = str(submit_mode or "").strip().lower()

    if normalized_category == "network_issue":
        return "network_issue"
    if normalized_category == "cheating_detected":
        return "cheating_detected"
    if normalized_category == "admin_decision":
        return "admin_decision"
    if normalized_submit_mode == "user_submit":
        return "user_submit"
    if normalized_submit_mode in {"auto_violation", "force_submit"}:
        return "cheating_detected"
    if normalized_submit_mode == "admin_force_submit":
        return "admin_decision"
    if normalized_status in {"submitted", "completed"}:
        return "user_submit"
    return "unknown"


# === Endpoints ===


@router.get("/runtime-policy")
async def get_runtime_policy_endpoint(
    current_user: User = Depends(get_current_user),
):
    """Runtime client policy for dynamic polling/autosave behavior."""
    _ = current_user  # authenticated-only endpoint
    return await get_runtime_policy(force_refresh=False)

@router.get("/violations")
async def get_violations_dashboard(
    exam_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    summary_only: bool = False,
    counted_only: bool = False,
    detail_level: str = "auto",
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Get violation dashboard statistics.

    Returns:
    - Total violations by type (tab_switch, copy, screenshot, etc.)
    - Top offenders (students with most violations)
    - Timeline breakdown (hourly)
    - Filters: by exam, date range
    """

    effective_from, effective_to = _coerce_violations_date_range(date_from, date_to)
    include_warning_only = not bool(counted_only)
    normalized_detail_level = (detail_level or "auto").strip().lower()
    if normalized_detail_level not in {"auto", "summary", "detail"}:
        raise HTTPException(status_code=400, detail="detail_level harus auto, summary, atau detail")

    if summary_only:
        return await _build_violations_summary_payload(
            db,
            exam_id=exam_id,
            date_from=effective_from,
            date_to=effective_to,
            current_user=current_user,
            include_warning_only=include_warning_only,
        )

    aggregate_first = normalized_detail_level == "summary" or (
        normalized_detail_level == "auto"
        and (
            settings.exam_peak_mode
            or str(settings.admin_monitoring_detail_level).lower() == "summary"
        )
    )
    if aggregate_first:
        selected_exam_title = await _resolve_selected_exam_title(
            db,
            exam_id=exam_id,
            current_user=current_user,
        )
        return await _build_violations_aggregate_payload(
            db,
            exam_id=exam_id,
            date_from=effective_from,
            date_to=effective_to,
            current_user=current_user,
            include_warning_only=include_warning_only,
            selected_exam_title=selected_exam_title,
        )

    result = await db.execute(
        _build_violations_query(
            exam_id=exam_id,
            date_from=effective_from,
            date_to=effective_to,
            current_user=current_user,
            include_warning_only=include_warning_only,
        )
    )
    logs = result.scalars().all()
    selected_exam_title = await _resolve_selected_exam_title(
        db,
        exam_id=exam_id,
        current_user=current_user,
    )
    return _build_violations_dashboard_payload(
        logs,
        exam_id=exam_id,
        date_from=effective_from,
        date_to=effective_to,
        selected_exam_title=selected_exam_title,
    )


@router.get("/violations/export")
async def export_violations_dashboard(
    exam_id: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    counted_only: bool = False,
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_read),
):
    require_feature_enabled(
        settings.heavy_exports_active,
        "heavy_export",
        status_code=503,
        message="Ekspor berat sedang dinonaktifkan selama mode ujian/puncak.",
    )
    effective_from, effective_to = _coerce_violations_date_range(date_from, date_to)
    include_warning_only = not bool(counted_only)
    result = await db.execute(
        _build_violations_query(
            exam_id=exam_id,
            date_from=effective_from,
            date_to=effective_to,
            current_user=current_user,
            include_warning_only=include_warning_only,
        )
    )
    logs = result.scalars().all()
    selected_exam_title = await _resolve_selected_exam_title(
        db,
        exam_id=exam_id,
        current_user=current_user,
    )
    payload = _build_violations_dashboard_payload(
        logs,
        exam_id=exam_id,
        date_from=effective_from,
        date_to=effective_to,
        selected_exam_title=selected_exam_title,
    )
    from app.core.pdf_generator import REPORTLAB_AVAILABLE, generate_violations_report_pdf

    if not REPORTLAB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Ekspor PDF belum tersedia di server ini")
    content = generate_violations_report_pdf(payload)
    media_type = "application/pdf"
    filename = _build_violations_export_filename()

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-store",
    }
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/exam/{exam_id}/live-stats")
async def get_live_exam_stats(
    exam_id: int,
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Get real-time statistics for an active exam.

    Returns:
    - Number of active/completed participants
    - Total violations
    - Average score (for completed)
    - Average progress
    """

    # Verify exam exists and user has access
    exam_result = await db.execute(
        select(
            Exam.id,
            Exam.title,
            Exam.creator_id,
        ).where(Exam.id == exam_id)
    )
    exam_row = exam_result.first()

    if not exam_row:
        raise HTTPException(404, "Exam not found")

    exam_title = str(exam_row.title or f"Ujian #{exam_id}")
    exam_creator_id = int(exam_row.creator_id or 0)
    if is_teacher_scope_restricted(current_user) and exam_creator_id != current_user.id:
        raise HTTPException(403, "Not authorized to monitor this exam")

    # Get all sessions for this exam (projection only, avoid loading ORM relations)
    sessions_result = await db.execute(
        select(
            ExamSession.id.label("session_id"),
            ExamSession.status.label("status"),
            ExamSession.score.label("score"),
            ExamSession.violation_count.label("violation_count"),
        ).where(ExamSession.exam_id == exam_id)
    )
    session_rows = sessions_result.fetchall()
    session_ids = [int(row.session_id) for row in session_rows if row.session_id]
    answered_count_map = await _get_answered_count_map(db, session_ids)

    active = [row for row in session_rows if row.status == 'in_progress']
    completed = [row for row in session_rows if row.status in ('completed', 'submitted')]

    # Calculate average score
    scores = [float(row.score) for row in completed if row.score is not None]
    avg_score = sum(scores) / len(scores) if scores else 0

    # Calculate average progress (based on answers submitted)
    # Get total questions for this exam
    questions_result = await db.execute(
        select(func.count(Question.id)).where(Question.exam_id == exam_id)
    )
    total_questions = questions_result.scalar() or 1

    progresses = []
    for row in session_rows:
        if row.status == 'in_progress':
            answered = answered_count_map.get(int(row.session_id), 0)
            progress = (answered / total_questions) * 100 if total_questions > 0 else 0
            progresses.append(progress)

    avg_progress = sum(progresses) / len(progresses) if progresses else 0

    # Total violations
    total_violations = sum(int(row.violation_count or 0) for row in session_rows)

    return LiveExamStats(
        exam_id=exam_id,
        exam_title=exam_title,
        active_participants=len(active),
        completed_participants=len(completed),
        total_violations=total_violations,
        average_score=round(avg_score, 2),
        average_progress=round(avg_progress, 2),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.get("/exam/{exam_id}/sessions")
async def get_exam_sessions(
    exam_id: int,
    status: Optional[str] = None,  # in_progress, completed, submitted
    include_recovery: bool = False,
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Get detailed session list for an exam.

    Returns list of all participants with their status, progress, and violations.
    """

    # Verify exam exists and user has access (lightweight column query)
    exam_result = await db.execute(
        select(
            Exam.id,
            Exam.title,
            Exam.creator_id,
        ).where(Exam.id == exam_id)
    )
    exam_row = exam_result.first()

    if not exam_row:
        raise HTTPException(404, "Exam not found")

    exam_title = str(exam_row.title or f"Ujian #{exam_id}")
    exam_creator_id = int(exam_row.creator_id or 0)
    if is_teacher_scope_restricted(current_user) and exam_creator_id != current_user.id:
        raise HTTPException(403, "Not authorized to monitor this exam")

    # Get total questions
    questions_result = await db.execute(
        select(func.count(Question.id)).where(Question.exam_id == exam_id)
    )
    total_questions = questions_result.scalar() or 1

    session_list: List[SessionStatus] = []
    summary_total = 0
    summary_in_progress = 0
    summary_completed = 0
    answered_count_map: Dict[int, int] = {}
    now = datetime.now(timezone.utc)

    if include_recovery:
        # Full path with recovery context (slower, used only when explicitly requested).
        query = (
            select(ExamSession)
            .options(
                selectinload(ExamSession.user),
            )
            .where(ExamSession.exam_id == exam_id)
        )
        if status:
            query = query.where(ExamSession.status == status)
        query = query.order_by(ExamSession.start_time.desc())

        result = await db.execute(query)
        sessions = result.scalars().all()
        session_ids = [int(s.id) for s in sessions if s.id]
        answered_count_map = await _get_answered_count_map(db, session_ids)

        session_logs: Dict[int, List[ExamLog]] = {}
        if session_ids:
            recovery_event_types = [
                "FORCE_SUBMIT_BY_TEACHER",
                "SESSION_TERMINATED",
                "SESSION_FORCE_KICK",
                "SESSION_MANUAL_RESET",
                "SESSION_RESET_BLOCKED",
                "EXAM_SUBMITTED",
                "AUTO_SUBMIT_VIOLATION",
            ]
            logs_result = await db.execute(
                select(ExamLog)
                .where(
                    ExamLog.session_id.in_(session_ids),
                    ExamLog.event_type.in_(recovery_event_types),
                )
                .order_by(ExamLog.created_at.desc(), ExamLog.id.desc())
            )
            logs_seen: Dict[int, int] = {}
            for log in logs_result.scalars().all():
                sid = int(log.session_id)
                if logs_seen.get(sid, 0) >= 20:
                    continue
                session_logs.setdefault(sid, []).append(log)
                logs_seen[sid] = logs_seen.get(sid, 0) + 1

        activity_by_user = await _get_bulk_session_activity(
            exam_id,
            [s.user.id for s in sessions if s.user],
        )

        for s in sessions:
            if not s.user:
                continue
            answered = answered_count_map.get(int(s.id), 0)
            progress = (answered / total_questions) * 100 if total_questions > 0 else 0
            recovery_status = evaluate_session_recovery(s, session_logs.get(int(s.id), []))

            is_online = False
            last_active_str = None
            activity = activity_by_user.get(s.user.id)
            if activity:
                last_active_str = activity.get("last_active")
                last_active = _parse_iso_timestamp(last_active_str)
                if last_active and (now - last_active).total_seconds() < 60:
                    is_online = True

            session_list.append(SessionStatus(
                session_id=s.id,
                user_id=s.user.id,
                user_name=s.user.full_name or s.user.username or f"User #{s.user.id}",
                user_class=s.user.student_class,
                progress=round(progress, 2),
                violation_count=s.violation_count or 0,
                start_time=s.start_time.isoformat() if s.start_time else "",
                status=s.status,
                ip_address=str(s.ip_address) if s.ip_address else None,
                is_online=is_online,
                last_active=last_active_str,
                terminated_by_admin=bool(s.terminated_by_admin),
                recovery_category=recovery_status.get("category"),
                recovery_message=recovery_status.get("message"),
                allow_continue=bool(recovery_status.get("allow_continue")),
            ))

        summary_total = len(sessions)
        summary_in_progress = len([s for s in sessions if s.status == 'in_progress'])
        summary_completed = len([s for s in sessions if s.status in ('completed', 'submitted')])
    else:
        # Optimized default path for monitoring table.
        session_query = (
            select(
                ExamSession.id.label("session_id"),
                ExamSession.user_id.label("user_id"),
                User.full_name.label("full_name"),
                User.username.label("username"),
                User.student_class.label("student_class"),
                ExamSession.start_time.label("start_time"),
                ExamSession.status.label("status"),
                ExamSession.violation_count.label("violation_count"),
                ExamSession.ip_address.label("ip_address"),
                ExamSession.terminated_by_admin.label("terminated_by_admin"),
            )
            .join(User, User.id == ExamSession.user_id)
            .where(ExamSession.exam_id == exam_id)
            .order_by(ExamSession.start_time.desc())
        )
        if status:
            session_query = session_query.where(ExamSession.status == status)

        rows_result = await db.execute(session_query)
        rows = rows_result.fetchall()
        session_ids = [int(row.session_id) for row in rows if row.session_id is not None]
        user_ids = [int(row.user_id) for row in rows if row.user_id is not None]
        answered_count_map = await _get_answered_count_map(db, session_ids)

        activity_by_user = await _get_bulk_session_activity(exam_id, user_ids)

        for row in rows:
            session_id = int(row.session_id)
            user_id = int(row.user_id)
            answered = answered_count_map.get(session_id, 0)
            progress = (answered / total_questions) * 100 if total_questions > 0 else 0

            is_online = False
            last_active_str = None
            activity = activity_by_user.get(user_id)
            if activity:
                last_active_str = activity.get("last_active")
                last_active = _parse_iso_timestamp(last_active_str)
                if last_active and (now - last_active).total_seconds() < 60:
                    is_online = True

            status_value = str(row.status or "")
            session_list.append(SessionStatus(
                session_id=session_id,
                user_id=user_id,
                user_name=row.full_name or row.username or f"User #{user_id}",
                user_class=row.student_class,
                progress=round(progress, 2),
                violation_count=int(row.violation_count or 0),
                start_time=row.start_time.isoformat() if row.start_time else "",
                status=status_value,
                ip_address=str(row.ip_address) if row.ip_address else None,
                is_online=is_online,
                last_active=last_active_str,
                terminated_by_admin=bool(row.terminated_by_admin),
                recovery_category=None,
                recovery_message=None,
                allow_continue=not bool(row.terminated_by_admin),
            ))

            summary_total += 1
            if status_value == "in_progress":
                summary_in_progress += 1
            if status_value in ("completed", "submitted"):
                summary_completed += 1

    return {
        "exam_id": exam_id,
        "exam_title": exam_title,
        "total_questions": total_questions,
        "sessions": [s.model_dump() for s in session_list],
        "summary": {
            "total": summary_total,
            "in_progress": summary_in_progress,
            "completed": summary_completed,
        }
    }


@router.get("/exam/{exam_id}/delta")
async def get_exam_monitor_delta(
    exam_id: int,
    last_id: str = Query(default="0-0"),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_read),
):
    """
    Lightweight delta feed for monitoring clients.

    Clients send the latest stream ID they have (`last_id`) and receive only
    incremental events after that cursor.
    """
    exam_result = await db.execute(
        select(
            Exam.id,
            Exam.creator_id,
        ).where(Exam.id == exam_id)
    )
    exam_row = exam_result.first()
    if not exam_row:
        raise HTTPException(404, "Exam not found")

    exam_creator_id = int(exam_row.creator_id or 0)
    if is_teacher_scope_restricted(current_user) and exam_creator_id != current_user.id:
        raise HTTPException(403, "Not authorized to monitor this exam")

    events, next_last_id = await read_monitoring_delta(
        exam_id,
        last_id=last_id,
        limit=limit,
    )
    return {
        "exam_id": int(exam_id),
        "count": len(events),
        "next_last_id": next_last_id,
        "events": events,
    }


@router.get("/active-exams")
async def get_active_exams(
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Get list of currently active exams (within time window and published).

    Used for the monitoring dashboard to show which exams can be monitored.
    """

    cache_key = _active_exams_cache_key(current_user)
    cached_payload = _get_active_exams_cached(cache_key)
    if cached_payload is not None:
        return cached_payload

    now = datetime.now(timezone.utc)

    query = (
        select(Exam)
        .where(
            Exam.is_deleted == False,
            Exam.is_published == True,
            Exam.start_time <= now,
            Exam.end_time >= now
        )
    )

    # Teacher can only see their own exams
    if is_teacher_scope_restricted(current_user):
        query = query.where(Exam.creator_id == current_user.id)

    query = query.order_by(Exam.start_time.desc())

    result = await db.execute(query)
    exams = result.scalars().all()
    exam_ids = [exam.id for exam in exams]
    exam_session_stats: Dict[int, Dict[str, int]] = {}

    if exam_ids:
        session_stats_result = await db.execute(
            select(
                ExamSession.exam_id,
                func.count(ExamSession.id).label("total_sessions"),
                func.sum(
                    case((ExamSession.status == "in_progress", 1), else_=0)
                ).label("in_progress_count"),
                func.sum(
                    case(
                        (ExamSession.status.in_(("completed", "submitted")), 1),
                        else_=0,
                    )
                ).label("completed_count"),
                func.coalesce(func.sum(ExamSession.violation_count), 0).label("total_violations"),
            )
            .where(
                ExamSession.exam_id.in_(exam_ids),
            )
            .group_by(ExamSession.exam_id)
        )
        exam_session_stats = {
            int(exam_id): {
                "total_sessions": int(total_sessions or 0),
                "in_progress_count": int(in_progress_count or 0),
                "completed_count": int(completed_count or 0),
                "total_violations": int(total_violations or 0),
            }
            for exam_id, total_sessions, in_progress_count, completed_count, total_violations in session_stats_result.fetchall()
        }

    active_exams = []
    for exam in exams:
        stats = exam_session_stats.get(exam.id, {})
        active_exams.append({
            "id": exam.id,
            "title": exam.title,
            "start_time": exam.start_time.isoformat() if exam.start_time else None,
            "end_time": exam.end_time.isoformat() if exam.end_time else None,
            "duration_minutes": exam.duration_minutes,
            "total_sessions": stats.get("total_sessions", 0),
            "active_participants": stats.get("in_progress_count", 0),
            "in_progress_count": stats.get("in_progress_count", 0),
            "completed_count": stats.get("completed_count", 0),
            "completed_participants": stats.get("completed_count", 0),
            "total_violations": stats.get("total_violations", 0),
        })

    payload = {
        "active_exams": active_exams,
        "total": len(active_exams),
        "total_sessions": sum(item["total_sessions"] for item in active_exams),
        "total_active_participants": sum(item["active_participants"] for item in active_exams),
        "total_completed_participants": sum(item["completed_count"] for item in active_exams),
        "total_violations": sum(item["total_violations"] for item in active_exams),
        "timestamp": now.isoformat()
    }
    _set_active_exams_cache(cache_key, payload)
    return payload


@router.get("/violation-types")
async def get_violation_types():
    """
    Get list of all violation types for filtering.
    """
    return {
        "violation_types": [
            {
                "key": key,
                "label": meta["label"],
                "severity": meta["severity"],
                "category": meta["category"],
                "description": meta["description"],
            }
            for key, meta in sorted(VIOLATION_TYPE_METADATA.items())
        ]
    }


# === Session Control Endpoints ===


@router.post("/sessions/{session_id}/kick")
async def kick_student_from_exam(
    session_id: int,
    request: KickStudentRequest,
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_write)
):
    """
    Force kick a student from an exam session.

    This marks the session as terminated-by-admin and sends a WebSocket notification
    to the student's device to force logout.
    """
    from app.core.redis_pubsub import publish_message
    logger.info(
        "Kick request received: session_id=%s actor=%s role=%s",
        session_id,
        current_user.username,
        current_user.role,
    )

    try:
        # Get session
        result = await db.execute(
            select(ExamSession)
            .options(selectinload(ExamSession.exam), selectinload(ExamSession.user))
            .where(ExamSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if not session:
            logger.warning("Kick rejected: session %s not found", session_id)
            raise HTTPException(404, "Session not found")

        # Verify access
        if is_teacher_scope_restricted(current_user) and session.exam.creator_id != current_user.id:
            logger.warning(
                "Kick forbidden: teacher_id=%s session_id=%s exam_id=%s",
                current_user.id,
                session_id,
                session.exam_id,
            )
            raise HTTPException(403, "Not authorized to control this exam")

        # DB CHECK constraint does not allow "kicked" status.
        # Use "terminated" + terminated_by_admin flag as canonical persisted state.
        session.status = 'terminated'
        session.terminated_by_admin = True
        if not session.end_time:
            session.end_time = datetime.now(timezone.utc)
        session.violation_count = (session.violation_count or 0) + 1
        db.add(
            ExamLog(
                session_id=session.id,
                event_type="SESSION_FORCE_KICK",
                event_data={
                    "category": "admin_decision",
                    "allow_continue": False,
                    "reason": request.reason,
                    "message": "Sesi dihentikan oleh pengawas/admin.",
                    "actor_id": current_user.id,
                    "actor_username": current_user.username,
                },
            )
        )
        await db.commit()

        # Log admin action for audit trail
        from app.api.activity import log_activity
        await log_activity(
            db=db,
            user_id=current_user.id,
            event_type="admin_kick_student",
            event_data={
                "session_id": session_id,
                "student_id": session.user_id,
                "student_name": session.user.full_name if session.user else "Unknown",
                "exam_id": session.exam_id,
                "exam_title": session.exam.title if session.exam else "Unknown",
                "reason": request.reason
            }
        )
        await db.commit()

        logger.info(
            "Session terminated by admin: session_id=%s user_id=%s exam_id=%s",
            session_id,
            session.user_id,
            session.exam_id,
        )

        # Get user name safely
        user_name = "Siswa"
        if session.user:
            user_name = session.user.full_name or session.user.username or "Siswa"

        # Send kick notification via Redis
        try:
            channel = f"exam_student_{session.exam_id}_{session.user_id}"
            logger.debug("Publishing kick event to channel=%s", channel)

            await publish_message(channel, {
                "type": "force_kick",
                "reason": request.reason,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            # Notify monitors
            await publish_message(f"exam_monitor_{session.exam_id}", {
                "type": "student_kicked",
                "user_id": session.user_id,
                "session_id": session_id,
                "reason": request.reason,
                "recovery_category": "admin_decision",
                "allow_continue": False,
                "kicked_by": current_user.username,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            logger.debug("Kick notifications published for session_id=%s", session_id)
        except Exception as e:
            # Log error but don't fail - session is already updated
            logger.error("Kick notification publish failed for session_id=%s: %s", session_id, e)

        return {
            "success": True,
            "message": f"Student {user_name} telah dikeluarkan dari ujian",
            "session_id": session_id,
            "user_id": session.user_id,
            "reason": request.reason
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error while kicking session_id=%s: %s", session_id, e)
        raise HTTPException(500, "Internal server error")


@router.get("/sessions/{session_id}/recovery-status")
async def get_session_recovery_status(
    session_id: int,
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_read),
):
    """Inspect why a session was disconnected and whether it may continue."""
    result = await db.execute(
        select(ExamSession)
        .options(selectinload(ExamSession.exam), selectinload(ExamSession.user))
        .where(ExamSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")

    if is_teacher_scope_restricted(current_user) and session.exam.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Tidak memiliki akses ke sesi ini")

    logs_result = await db.execute(
        select(ExamLog)
        .where(ExamLog.session_id == session.id)
        .order_by(ExamLog.created_at.desc(), ExamLog.id.desc())
        .limit(30)
    )
    logs = logs_result.scalars().all()
    recovery = evaluate_session_recovery(session, logs)

    return {
        "session_id": session.id,
        "exam_id": session.exam_id,
        "user_id": session.user_id,
        "status": session.status,
        "terminated_by_admin": bool(session.terminated_by_admin),
        "recovery_category": recovery.get("category"),
        "allow_continue": bool(recovery.get("allow_continue")),
        "message": recovery.get("message"),
        "recommended_action": (
            "allow_continue"
            if recovery.get("allow_continue")
            else "block_relogin"
        ),
    }


@router.post("/sessions/{session_id}/reset")
async def reset_session_after_disconnect(
    session_id: int,
    payload: SessionResetRequest,
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_write),
):
    """
    Reset session so student can continue only for non-intentional disconnect.
    """
    from app.core.redis_pubsub import publish_message

    result = await db.execute(
        select(ExamSession)
        .options(selectinload(ExamSession.exam), selectinload(ExamSession.user))
        .where(ExamSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")

    if is_teacher_scope_restricted(current_user) and session.exam.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Tidak memiliki akses ke sesi ini")

    logs_result = await db.execute(
        select(ExamLog)
        .where(ExamLog.session_id == session.id)
        .order_by(ExamLog.created_at.desc(), ExamLog.id.desc())
        .limit(30)
    )
    logs = logs_result.scalars().all()
    recovery = evaluate_session_recovery(session, logs)

    if not recovery.get("allow_continue"):
        db.add(
            ExamLog(
                session_id=session.id,
                event_type="SESSION_RESET_BLOCKED",
                event_data={
                    "category": recovery.get("category"),
                    "allow_continue": False,
                    "reason": payload.reason or "Recovery policy blocked",
                    "message": recovery.get("message"),
                    "actor_id": current_user.id,
                    "actor_username": current_user.username,
                },
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "error": "SESSION_RESET_BLOCKED",
                "category": recovery.get("category"),
                "allow_continue": False,
                "message": recovery.get("message"),
            },
        )

    previous_status = session.status
    session.status = "in_progress"
    session.end_time = None
    session.terminated_by_admin = False
    session.emergency_exit_allowed = False

    db.add(
        ExamLog(
            session_id=session.id,
            event_type="SESSION_MANUAL_RESET",
            event_data={
                "category": recovery.get("category"),
                "allow_continue": True,
                "reason": payload.reason or "Manual reset for disconnection recovery",
                "message": recovery.get("message"),
                "actor_id": current_user.id,
                "actor_username": current_user.username,
                "previous_status": previous_status,
            },
        )
    )
    await db.commit()

    try:
        await publish_message(
            f"exam_student_{session.exam_id}_{session.user_id}",
            {
                "type": "session_reset_allowed",
                "session_id": session.id,
                "reason": payload.reason or "Koneksi terputus - sesi dilanjutkan",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await publish_message(
            f"exam_monitor_{session.exam_id}",
            {
                "type": "student_session_reset",
                "session_id": session.id,
                "user_id": session.user_id,
                "recovery_category": recovery.get("category"),
                "allow_continue": True,
                "message": recovery.get("message"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        logger.warning("Failed to publish session reset notifications: %s", exc)

    return {
        "success": True,
        "session_id": session.id,
        "user_id": session.user_id,
        "exam_id": session.exam_id,
        "status": session.status,
        "recovery_category": recovery.get("category"),
        "allow_continue": True,
        "message": "Sesi berhasil di-reset. Siswa dapat login kembali dan melanjutkan ujian.",
    }


@router.get(
    "/exam/{exam_id}/recovery-candidates",
    response_model=RecoveryCandidatesResponse,
)
async def get_exam_recovery_candidates(
    exam_id: int,
    limit: int = 400,
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_read),
):
    """List candidate sessions for manual reopen/recovery decision."""
    exam_result = await db.execute(
        select(Exam.id, Exam.title, Exam.creator_id).where(Exam.id == exam_id)
    )
    exam_row = exam_result.first()
    if not exam_row:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    exam_title = str(exam_row.title or f"Ujian #{exam_id}")
    exam_creator_id = int(exam_row.creator_id or 0)
    if is_teacher_scope_restricted(current_user) and exam_creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Tidak memiliki akses ke ujian ini")

    safe_limit = max(50, min(int(limit or 400), 1000))
    sessions_result = await db.execute(
        select(ExamSession)
        .options(selectinload(ExamSession.user), selectinload(ExamSession.exam))
        .where(
            ExamSession.exam_id == exam_id,
            ExamSession.status.in_(tuple(RECOVERY_TERMINAL_STATUSES)),
        )
        .order_by(ExamSession.start_time.desc(), ExamSession.id.desc())
        .limit(safe_limit)
    )
    sessions = sessions_result.scalars().all()
    session_ids = [int(s.id) for s in sessions if s.id]

    logs_by_session: Dict[int, List[ExamLog]] = {}
    if session_ids:
        logs_result = await db.execute(
            select(ExamLog)
            .where(
                ExamLog.session_id.in_(session_ids),
                ExamLog.event_type.in_(tuple(RECOVERY_RELEVANT_EVENTS)),
            )
            .order_by(ExamLog.created_at.desc(), ExamLog.id.desc())
        )
        seen: Dict[int, int] = {}
        for log in logs_result.scalars().all():
            sid = int(log.session_id or 0)
            if sid <= 0:
                continue
            if seen.get(sid, 0) >= 20:
                continue
            logs_by_session.setdefault(sid, []).append(log)
            seen[sid] = seen.get(sid, 0) + 1

    candidates: List[RecoveryCandidate] = []
    summary = {
        "network_issue": 0,
        "cheating_detected": 0,
        "admin_decision": 0,
        "user_submit": 0,
        "unknown": 0,
        "allow_continue": 0,
        "blocked": 0,
    }

    for session in sessions:
        if not session.user:
            continue
        sid = int(session.id)
        logs = logs_by_session.get(sid, [])
        recovery = evaluate_session_recovery(session, logs)
        recovery_category = str(recovery.get("category") or "unknown").lower()
        submit_mode = _derive_submit_mode(logs)
        reason_bucket = _derive_reason_bucket(
            status=str(session.status or ""),
            recovery_category=recovery_category,
            submit_mode=submit_mode,
        )

        allow_continue = bool(recovery.get("allow_continue"))
        can_override = bool(
            current_user.role in {"admin", "teacher"}
            and not allow_continue
        )
        if reason_bucket not in summary:
            summary[reason_bucket] = 0
        summary[reason_bucket] += 1
        summary["allow_continue" if allow_continue else "blocked"] += 1

        last_log = logs[0] if logs else None
        last_event_type = _log_event_type(last_log) if last_log else None
        last_event_at = (
            _ensure_aware_datetime(last_log.created_at).isoformat()
            if last_log and getattr(last_log, "created_at", None)
            else None
        )
        candidates.append(
            RecoveryCandidate(
                session_id=sid,
                user_id=int(session.user_id),
                user_name=session.user.full_name or session.user.username or f"User #{session.user_id}",
                user_class=session.user.student_class,
                status=str(session.status or ""),
                violation_count=int(session.violation_count or 0),
                started_at=(
                    _ensure_aware_datetime(session.start_time).isoformat()
                    if session.start_time else None
                ),
                ended_at=(
                    _ensure_aware_datetime(session.end_time).isoformat()
                    if session.end_time else None
                ),
                recovery_category=recovery_category or "unknown",
                recovery_message=str(recovery.get("message") or ""),
                submit_mode=submit_mode,
                reason_bucket=reason_bucket,
                reason_label=RECOVERY_REASON_LABELS.get(reason_bucket, "Perlu verifikasi"),
                allow_continue=allow_continue,
                can_override=can_override,
                last_event_type=last_event_type,
                last_event_at=last_event_at,
            )
        )

    candidates.sort(
        key=lambda row: (
            0 if row.allow_continue else 1,
            RECOVERY_REASON_SORT.get(row.reason_bucket, 99),
            -(int(row.violation_count or 0)),
            str(row.user_name or ""),
        )
    )

    return RecoveryCandidatesResponse(
        exam_id=exam_id,
        exam_title=exam_title,
        total_candidates=len(candidates),
        summary=summary,
        candidates=candidates,
    )


@router.post("/sessions/{session_id}/reopen-override")
async def reopen_session_with_override(
    session_id: int,
    payload: SessionOverrideResetRequest,
    current_user: User = Depends(get_current_exam_monitor),
    db: AsyncSession = Depends(get_db_write),
):
    """
    Override to reopen blocked sessions for admin / teacher exam owner.
    Keep audit trail for exceptional manual reopen.
    """
    from app.core.redis_pubsub import publish_message

    result = await db.execute(
        select(ExamSession)
        .options(selectinload(ExamSession.exam), selectinload(ExamSession.user))
        .where(ExamSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesi tidak ditemukan")

    now = datetime.now(timezone.utc)
    exam = session.exam
    if not exam:
        raise HTTPException(status_code=409, detail="Data ujian tidak tersedia untuk sesi ini")
    if is_teacher_scope_restricted(current_user) and exam.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Tidak memiliki akses ke sesi ini")
    if exam.is_deleted or not exam.is_published:
        raise HTTPException(status_code=409, detail="Ujian tidak aktif untuk reopen override")
    if exam.end_time and _ensure_aware_datetime(exam.end_time) and _ensure_aware_datetime(exam.end_time) < now:
        raise HTTPException(status_code=409, detail="Ujian sudah berakhir, override reopen ditolak")

    logs_result = await db.execute(
        select(ExamLog)
        .where(ExamLog.session_id == session.id)
        .order_by(ExamLog.created_at.desc(), ExamLog.id.desc())
        .limit(30)
    )
    logs = logs_result.scalars().all()
    recovery = evaluate_session_recovery(session, logs)
    previous_status = str(session.status or "")
    previous_violation_count = int(session.violation_count or 0)

    session.status = "in_progress"
    session.end_time = None
    session.score = None
    session.terminated_by_admin = False
    session.emergency_exit_allowed = False
    session.is_paused = False
    session.paused_at = None
    session.total_paused_seconds = 0
    if payload.reset_violation_count:
        session.violation_count = 0
    db.add(
        ExamLog(
            session_id=session.id,
            event_type="SESSION_ADMIN_OVERRIDE_REOPEN",
            event_data={
                "category": recovery.get("category"),
                "allow_continue_before_override": bool(recovery.get("allow_continue")),
                "reason": payload.reason or "Override pengawas",
                "actor_id": current_user.id,
                "actor_username": current_user.username,
                "actor_role": current_user.role,
                "previous_status": previous_status,
                "previous_violation_count": previous_violation_count,
                "reset_violation_count": bool(payload.reset_violation_count),
            },
        )
    )
    await db.commit()

    try:
        await publish_message(
            f"exam_student_{session.exam_id}_{session.user_id}",
            {
                "type": "session_reopened_override",
                "session_id": session.id,
                "reason": payload.reason or "Override pengawas",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await publish_message(
            f"exam_monitor_{session.exam_id}",
            {
                "type": "student_session_reopened_override",
                "session_id": session.id,
                "user_id": session.user_id,
                "previous_status": previous_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        logger.warning("Failed to publish override reopen notification: %s", exc)

    return {
        "success": True,
        "session_id": session.id,
        "user_id": session.user_id,
        "exam_id": session.exam_id,
        "status": session.status,
        "message": "Sesi berhasil dibuka ulang dengan override pengawas.",
    }


# === System Metrics Endpoints ===


@router.get("/system/ops-summary")
async def get_system_ops_summary(
    request: Request,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_read),
):
    """
    Selective live ops summary for admin monitoring.

    Scope intentionally limited to high-signal indicators:
    edge/frontend/backend/database/redis/host.
    """
    _ = current_user
    host_header = request.headers.get("host", "")
    summary = await get_ops_summary(host_header=host_header, db=db)
    if isinstance(summary, dict):
        payload = dict(summary)
        auto_tick = await run_auto_intelligence_tick(
            host_header=host_header,
            db=db,
            summary=payload,
            force=False,
            source="ops_summary_poll",
            actor=current_user.username,
        )
        if bool(((auto_tick.get("mode") or {}).get("changed"))):
            # mode change affects policy exposed in summary payload
            invalidate_ops_summary_cache()
            refreshed_summary = await get_ops_summary(host_header=host_header, db=db)
            if isinstance(refreshed_summary, dict):
                payload = dict(refreshed_summary)
        payload["restart_backend"] = _restart_backend_status()
        payload["auto_intelligence"] = {
            **(await get_auto_intelligence_status(force_refresh=True)),
            "tick": auto_tick,
        }
        return payload
    return summary

@router.get("/system/metrics")
async def get_system_metrics(
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_read)
):
    """
    Get comprehensive system metrics (CPU, Memory, Disk, Database, Redis, Application).
    Admin-only endpoint for system monitoring dashboard.
    """
    await metrics_collector.initialize()
    metrics = await metrics_collector.collect_all_metrics(db)
    return metrics


@router.get("/system/runtime-metrics")
async def get_runtime_metrics(
    current_user: User = Depends(get_current_active_admin),
):
    """
    Get rolling runtime metrics for incident prevention.

    Includes global 5xx rate, critical endpoint p95, runtime event spikes,
    and active runtime policy (normal/degraded).
    """
    _ = current_user
    runtime_snapshot = await get_runtime_snapshot(window_seconds=60, latency_window_seconds=180)
    policy = await get_runtime_policy(force_refresh=True)
    degrade_state = await get_degrade_mode_state(force_refresh=True)
    return {
        "runtime": runtime_snapshot,
        "policy": policy,
        "degrade_state": degrade_state,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/system/degrade-mode")
async def update_degrade_mode(
    payload: DegradeModeUpdate,
    current_user: User = Depends(get_current_active_admin),
):
    """Manually toggle peak-protection degrade mode."""
    ttl_minutes = max(5, min(int(payload.ttl_minutes or 120), 24 * 60))
    if payload.enabled:
        state = await set_degrade_mode(
            enabled=True,
            reason=payload.reason or "Manual peak protection",
            source="manual",
            actor=current_user.username,
            ttl_minutes=ttl_minutes,
        )
    else:
        state = await set_degrade_mode(
            enabled=False,
            reason=None,
            source="manual",
            actor=current_user.username,
        )
    invalidate_ops_summary_cache()

    return {
        "success": True,
        "message": "Degrade mode updated",
        "degrade_state": state,
        "policy": await get_runtime_policy(force_refresh=True),
        "updated_by": current_user.username,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/system/auto-restart-schedule")
async def update_auto_restart_schedule_endpoint(
    payload: AutoRestartScheduleUpdate,
    current_user: User = Depends(get_current_active_admin),
):
    """Update konfigurasi auto restart dan daftar jadwal one-off WIB."""
    schedule = await set_auto_restart_schedule(
        enabled=bool(payload.enabled),
        time_wib=payload.time_wib,
        restart_buffer_minutes=payload.restart_buffer_minutes,
        full_restart=bool(payload.full_restart),
        include_data_services=bool(payload.include_data_services),
        restart_timeout_seconds=payload.restart_timeout_seconds,
        scheduled_runs_wib=payload.scheduled_runs_wib,
        replace_runs=bool(payload.replace_runs),
        reason=payload.reason,
        source="manual",
        actor=current_user.username,
    )
    invalidate_ops_summary_cache()
    return {
        "success": True,
        "message": "Auto restart schedule updated",
        "schedule": schedule,
        "status": await get_auto_restart_status(force_refresh=True),
        "policy": await get_runtime_policy(force_refresh=True),
        "updated_by": current_user.username,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/system/auto-restart-schedule")
async def get_auto_restart_schedule_endpoint(
    current_user: User = Depends(get_current_active_admin),
):
    """Get konfigurasi auto restart terjadwal WIB."""
    _ = current_user
    return {
        "success": True,
        "schedule": await get_auto_restart_schedule(force_refresh=True),
        "status": await get_auto_restart_status(force_refresh=True),
        "policy": await get_runtime_policy(force_refresh=True),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/system/auto-restart-schedule/check")
async def run_auto_restart_check_now(
    payload: Optional[AutoRestartRunRequest] = None,
    current_user: User = Depends(get_current_active_admin),
):
    """
    Trigger evaluasi scheduler auto-restart.
    Bisa force + dry_run untuk uji coba aman tanpa restart sungguhan.
    """
    run_payload = payload or AutoRestartRunRequest()
    status = await run_auto_restart_scheduler_tick(
        force=bool(run_payload.force),
        dry_run=bool(run_payload.dry_run),
        reason=run_payload.reason or "Manual scheduler check dari monitoring dashboard",
        source="manual_dashboard",
        actor=current_user.username,
    )
    invalidate_ops_summary_cache()
    return {
        "success": True,
        "message": "Auto restart scheduler check executed",
        "status": status,
        "updated_by": current_user.username,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/system/resource-mode")
async def get_resource_mode(
    current_user: User = Depends(get_current_active_admin),
):
    """Get adaptive resource mode (Normal / High / Extreme)."""
    _ = current_user
    return {
        "success": True,
        "resource_mode": await get_resource_mode_state(force_refresh=True),
        "catalog": get_resource_mode_catalog(),
        "policy": await get_runtime_policy(force_refresh=True),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/system/resource-mode")
async def update_resource_mode(
    payload: ResourceModeUpdate,
    current_user: User = Depends(get_current_active_admin),
):
    """Set adaptive resource mode and broadcast consequences in response."""
    normalized_mode = str(payload.mode or "").strip().lower()
    if normalized_mode not in {"normal", "high", "extreme"}:
        raise HTTPException(
            status_code=400,
            detail="Mode tidak valid. Pilih: normal, high, atau extreme.",
        )

    ttl_minutes = max(5, min(int(payload.ttl_minutes or 120), 24 * 60))
    resource_state = await set_resource_mode(
        mode=normalized_mode,
        reason=payload.reason,
        source="manual",
        actor=current_user.username,
        ttl_minutes=ttl_minutes,
    )

    # Keep legacy degrade switch aligned for compatibility with older dashboards.
    if normalized_mode == "normal":
        await set_degrade_mode(
            enabled=False,
            reason=None,
            source="manual_resource_mode",
            actor=current_user.username,
        )
    else:
        await set_degrade_mode(
            enabled=True,
            reason=payload.reason or f"Resource mode {normalized_mode} enabled",
            source="manual_resource_mode",
            actor=current_user.username,
            ttl_minutes=ttl_minutes,
        )

    policy = await get_runtime_policy(force_refresh=True)
    invalidate_ops_summary_cache()
    return {
        "success": True,
        "message": f"Resource mode diubah ke {normalized_mode.upper()}",
        "resource_mode": resource_state,
        "policy": policy,
        "catalog": get_resource_mode_catalog(),
        "updated_by": current_user.username,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/system/auto-intelligence")
async def get_auto_intelligence(
    current_user: User = Depends(get_current_active_admin),
):
    """Get current intelligent auto mode/healing controls and runtime status."""
    _ = current_user
    return {
        "success": True,
        "auto_intelligence": await get_auto_intelligence_status(force_refresh=True),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/system/auto-intelligence")
async def update_auto_intelligence(
    payload: AutoIntelligenceControlUpdate,
    request: Request,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_read),
):
    """Update auto-performance / auto-healing controls and optionally trigger immediate tick."""
    if (
        payload.auto_mode_enabled is None
        and payload.auto_heal_enabled is None
        and not bool(payload.force_tick)
    ):
        raise HTTPException(
            status_code=400,
            detail="Tidak ada perubahan kontrol. Kirim auto_mode_enabled / auto_heal_enabled atau force_tick=true.",
        )

    await update_auto_intelligence_controls(
        auto_mode_enabled=payload.auto_mode_enabled,
        auto_heal_enabled=payload.auto_heal_enabled,
        actor=current_user.username,
        source="manual_dashboard",
        reason=payload.reason or "Manual control update from monitoring",
    )

    tick_result = None
    if bool(payload.force_tick):
        tick_result = await run_auto_intelligence_tick(
            host_header=request.headers.get("host", ""),
            db=db,
            force=True,
            source="manual_dashboard_toggle",
            actor=current_user.username,
            reason=payload.reason or "Manual force tick after control update",
        )
        if bool(((tick_result.get("mode") or {}).get("changed"))):
            invalidate_ops_summary_cache()

    return {
        "success": True,
        "message": "Auto intelligence controls updated",
        "auto_intelligence": await get_auto_intelligence_status(force_refresh=True),
        "tick": tick_result,
        "policy": await get_runtime_policy(force_refresh=True),
        "updated_by": current_user.username,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/system/auto-intelligence/run")
async def run_auto_intelligence_now(
    request: Request,
    payload: Optional[AutoIntelligenceRunRequest] = None,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_read),
):
    """Run intelligent auto mode/healing evaluation immediately."""
    run_payload = payload or AutoIntelligenceRunRequest()
    host_header = request.headers.get("host", "")
    tick_result = await run_auto_intelligence_tick(
        host_header=host_header,
        db=db,
        force=bool(run_payload.force),
        force_heal=bool(run_payload.force_heal),
        source="manual_dashboard_run",
        actor=current_user.username,
        reason=run_payload.reason or "Manual run auto intelligence from monitoring",
    )
    if bool(((tick_result.get("mode") or {}).get("changed"))):
        invalidate_ops_summary_cache()

    return {
        "success": True,
        "message": "Auto intelligence tick executed",
        "tick": tick_result,
        "auto_intelligence": await get_auto_intelligence_status(force_refresh=True),
        "policy": await get_runtime_policy(force_refresh=True),
        "updated_by": current_user.username,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/system/restart-safe")
async def restart_system_safely(
    payload: RestartSystemRequest,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_write),
):
    """
    Safe soft-restart for inter-session cleanup.

    Guardrails:
    - No active in-progress sessions
    - No currently running exams
    - No near-future exams within restart buffer window
    """
    now = datetime.now(timezone.utc)
    buffer_minutes = max(5, min(int(payload.restart_buffer_minutes or 30), 180))
    buffer_until = now + timedelta(minutes=buffer_minutes)
    restart_lock_acquired = False

    if not payload.dry_run:
        restart_lock_acquired = await _acquire_restart_safe_exec_lock(current_user.username)
        if not restart_lock_acquired:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "RESTART_ALREADY_IN_PROGRESS",
                    "message": "Restart sedang diproses oleh request lain. Tunggu beberapa saat lalu coba lagi.",
                },
            )

    try:
        active_sessions_count = int(
            (
                await db.execute(
                    select(func.count(ExamSession.id)).where(
                        ExamSession.status.in_(["in_progress", "active", "paused"])
                    )
                )
            ).scalar()
            or 0
        )

        running_exams_count = int(
            (
                await db.execute(
                    select(func.count(Exam.id)).where(
                        Exam.is_deleted == False,
                        Exam.is_published == True,
                        Exam.start_time <= now,
                        Exam.end_time >= now,
                    )
                )
            ).scalar()
            or 0
        )

        upcoming_exams_count = int(
            (
                await db.execute(
                    select(func.count(Exam.id)).where(
                        Exam.is_deleted == False,
                        Exam.is_published == True,
                        Exam.start_time > now,
                        Exam.start_time <= buffer_until,
                    )
                )
            ).scalar()
            or 0
        )

        guard_ok = (
            active_sessions_count == 0
            and running_exams_count == 0
            and upcoming_exams_count == 0
        )

        if not guard_ok:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "RESTART_GUARD_BLOCKED",
                    "message": (
                        "Restart diblokir karena masih ada sesi aktif/ujian berjalan atau "
                        "ujian terjadwal dalam waktu dekat."
                    ),
                    "active_sessions_count": active_sessions_count,
                    "running_exams_count": running_exams_count,
                    "upcoming_exams_count": upcoming_exams_count,
                    "buffer_minutes": buffer_minutes,
                },
            )

        last_exec = await _get_restart_safe_last_exec()
        cooldown_state = _build_restart_safe_cooldown_state(now, last_exec)

        if payload.full_restart and not payload.dry_run and bool(cooldown_state.get("active")):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "RESTART_COOLDOWN_ACTIVE",
                    "message": "Full restart masih dalam masa cooldown untuk mencegah restart beruntun saat jam ujian.",
                    "cooldown": cooldown_state,
                },
            )

        redis_patterns = [
            "exam_session:*",
            "exam_answers:*",
            "exam_activity:*",
            "cache:exam-results:*",
            "cache:exam-start-validation:*",
            "runtime:*",
            "degrade:throttle:*",
            "system:degrade_mode",
        ]
        restart_plan = _build_full_restart_services(payload.include_data_services)
        restart_backend = _restart_backend_status()

        if payload.dry_run:
            return {
                "success": True,
                "dry_run": True,
                "mode": "full" if payload.full_restart else "soft",
                "message": (
                    "Guard restart lolos. Sistem aman untuk restart FULL antar sesi."
                    if payload.full_restart
                    else "Guard restart lolos. Sistem aman untuk restart antar sesi."
                ),
                "checks": {
                    "active_sessions_count": active_sessions_count,
                    "running_exams_count": running_exams_count,
                    "upcoming_exams_count": upcoming_exams_count,
                    "buffer_minutes": buffer_minutes,
                },
                "cooldown": cooldown_state,
                "redis_patterns": redis_patterns,
                "restart_plan": restart_plan if payload.full_restart else [],
                "restart_backend": restart_backend,
                "include_data_services": bool(payload.include_data_services),
                "restart_timeout_seconds": max(60, min(int(payload.restart_timeout_seconds or 300), 1200)),
                "timestamp": now.isoformat(),
            }

        if payload.full_restart:
            _ensure_full_restart_available()

        deleted_keys = await _delete_redis_keys_by_patterns(redis_patterns)
        await set_resource_mode(
            mode="normal",
            reason=payload.reason or "System restart antar sesi",
            source="system_restart",
            actor=current_user.username,
            ttl_minutes=120,
        )
        await set_degrade_mode(
            enabled=False,
            reason=None,
            source="system_restart",
            actor=current_user.username,
        )

        full_restart_result: Optional[Dict[str, Any]] = None
        if payload.full_restart:
            try:
                full_restart_result = await _execute_full_restart(
                    include_data_services=bool(payload.include_data_services),
                    timeout_seconds=payload.restart_timeout_seconds,
                    actor=current_user.username,
                    reason=payload.reason,
                )
            except Exception as exc:
                logger.error("Full restart execution failed: %s", exc, exc_info=True)
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "FULL_RESTART_FAILED",
                        "message": f"Full restart gagal dijalankan: {str(exc)}",
                        "hint": _restart_backend_status()["hint"],
                    },
                )

        if payload.full_restart:
            await _set_restart_safe_last_exec(
                mode="full",
                actor=current_user.username,
                reason=payload.reason,
            )

        invalidate_ops_summary_cache()

        mode_label = "FULL" if payload.full_restart else "SOFT"
        return {
            "success": True,
            "mode": "full" if payload.full_restart else "soft",
            "message": (
                f"Restart {mode_label} antar sesi selesai. "
                "Cache runtime dibersihkan dan mode dikembalikan ke NORMAL."
            ),
            "cooldown": _build_restart_safe_cooldown_state(
                datetime.now(timezone.utc),
                {
                    "mode": "full",
                    "actor": current_user.username,
                    "at": datetime.now(timezone.utc).isoformat(),
                },
            )
            if payload.full_restart
            else cooldown_state,
            "redis_deleted_keys": deleted_keys,
            "full_restart": full_restart_result if payload.full_restart else None,
            "resource_mode": await get_resource_mode_state(force_refresh=True),
            "policy": await get_runtime_policy(force_refresh=True),
            "updated_by": current_user.username,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if restart_lock_acquired:
            await _release_restart_safe_exec_lock()


@router.get("/system/health")
async def get_system_health(
    current_user: User = Depends(get_current_active_admin)
):
    """
    Quick health check endpoint for system status.
    Returns: healthy/degraded/critical based on thresholds.
    """
    import psutil

    # Non-blocking sampling to keep dashboard polling responsive.
    cpu_percent = psutil.cpu_percent(interval=0.0)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    # Determine health status
    health = "healthy"
    warnings = []

    if cpu_percent > 80:
        health = "degraded"
        warnings.append(f"High CPU usage: {cpu_percent}%")
    if cpu_percent > 95:
        health = "critical"

    if memory.percent > 85:
        health = "degraded" if health == "healthy" else "critical"
        warnings.append(f"High memory usage: {memory.percent}%")

    if disk.percent > 90:
        health = "degraded" if health == "healthy" else "critical"
        warnings.append(f"Low disk space: {disk.percent}% used")

    return {
        "status": health,
        "warnings": warnings,
        "metrics": {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }



@router.post("/system/warmup")
async def system_warmup(
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_read)
):
    """System Warmup - wake up all services after idle periods."""
    import time as _time
    import psutil
    import logging
    logger = logging.getLogger(__name__)

    steps = []

    # Step 1: Redis PING (10%)
    t0 = _time.time()
    try:
        from app.core.redis_pubsub import get_redis
        redis = await get_redis()
        pong = await redis.ping()
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 1, "name": "Redis PING", "percent": 10,
            "status": "ok" if pong else "error",
            "detail": f"PONG received ({ms}ms)", "time_ms": ms})
    except Exception as e:
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 1, "name": "Redis PING", "percent": 10,
            "status": "error", "detail": str(e), "time_ms": ms})
        logger.warning(f"Warmup: Redis PING failed: {e}")

    # Step 2: Redis Read/Write (25%)
    t0 = _time.time()
    try:
        from app.core.redis_pubsub import get_redis
        redis = await get_redis()
        await redis.set("warmup:test", "warmup_ok", ex=10)
        val = await redis.get("warmup:test")
        await redis.delete("warmup:test")
        ms = round((_time.time() - t0) * 1000, 1)
        ok = val == "warmup_ok"
        steps.append({"step": 2, "name": "Redis Read/Write", "percent": 25,
            "status": "ok" if ok else "error",
            "detail": f"SET-GET-DEL pipeline OK ({ms}ms)" if ok else "Mismatch",
            "time_ms": ms})
    except Exception as e:
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 2, "name": "Redis Read/Write", "percent": 25,
            "status": "error", "detail": str(e), "time_ms": ms})

    # Step 3: PostgreSQL Connection (40%)
    t0 = _time.time()
    try:
        result = await db.execute(select(func.now()))
        _ = result.scalar()
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 3, "name": "PostgreSQL Connection", "percent": 40,
            "status": "ok", "detail": f"Connected ({ms}ms)", "time_ms": ms})
    except Exception as e:
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 3, "name": "PostgreSQL Connection", "percent": 40,
            "status": "error", "detail": str(e), "time_ms": ms})

    # Step 4: PostgreSQL Data Query (55%)
    t0 = _time.time()
    try:
        uc = (await db.execute(select(func.count(User.id)))).scalar() or 0
        ec = (await db.execute(select(func.count(Exam.id)).where(Exam.is_deleted == False))).scalar() or 0
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 4, "name": "PostgreSQL Data Query", "percent": 55,
            "status": "ok", "detail": f"{uc} users, {ec} exams ({ms}ms)", "time_ms": ms})
    except Exception as e:
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 4, "name": "PostgreSQL Data Query", "percent": 55,
            "status": "error", "detail": str(e), "time_ms": ms})

    # Step 5: Celery Worker (70%)
    t0 = _time.time()
    try:
        from app.tasks.scheduler import celery_app
        inspector = celery_app.control.inspect(timeout=3)
        active = inspector.active()
        ms = round((_time.time() - t0) * 1000, 1)
        if active is not None:
            steps.append({"step": 5, "name": "Celery Worker", "percent": 70,
                "status": "ok", "detail": f"{len(active)} worker(s) active ({ms}ms)", "time_ms": ms})
        else:
            steps.append({"step": 5, "name": "Celery Worker", "percent": 70,
                "status": "warning", "detail": f"No workers detected ({ms}ms)", "time_ms": ms})
    except Exception as e:
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 5, "name": "Celery Worker", "percent": 70,
            "status": "warning", "detail": f"Check skipped: {e}", "time_ms": ms})

    # Step 6: Disk Space (85%)
    t0 = _time.time()
    try:
        disk = psutil.disk_usage("/")
        free_gb = round(disk.free / (1024**3), 1)
        ms = round((_time.time() - t0) * 1000, 1)
        st = "ok" if disk.percent < 90 else ("warning" if disk.percent < 95 else "error")
        steps.append({"step": 6, "name": "Disk Space", "percent": 85,
            "status": st, "detail": f"{free_gb} GB free ({ms}ms)", "time_ms": ms})
    except Exception as e:
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 6, "name": "Disk Space", "percent": 85,
            "status": "error", "detail": str(e), "time_ms": ms})

    # Step 7: Memory (100%)
    t0 = _time.time()
    try:
        mem = psutil.virtual_memory()
        free_mb = round(mem.available / (1024**2))
        ms = round((_time.time() - t0) * 1000, 1)
        st = "ok" if mem.percent < 85 else ("warning" if mem.percent < 95 else "error")
        steps.append({"step": 7, "name": "Memory (RAM)", "percent": 100,
            "status": st, "detail": f"{free_mb} MB available ({ms}ms)", "time_ms": ms})
    except Exception as e:
        ms = round((_time.time() - t0) * 1000, 1)
        steps.append({"step": 7, "name": "Memory (RAM)", "percent": 100,
            "status": "error", "detail": str(e), "time_ms": ms})

    errs = sum(1 for s in steps if s["status"] == "error")
    warns = sum(1 for s in steps if s["status"] == "warning")
    total_ms = round(sum(s["time_ms"] for s in steps), 1)
    overall = "error" if errs > 0 else ("warning" if warns > 0 else "ok")
    logger.info(f"System warmup: {overall} ({total_ms}ms)")

    return {
        "overall": overall,
        "steps": steps,
        "total_time_ms": total_ms,
        "errors": errs,
        "warnings": warns,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
