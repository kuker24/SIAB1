"""
Admin Exam Control API endpoints.
Handles admin-only operations for exam management including
pause/resume, force complete, and session cleanup.
"""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
import logging

from app.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.models.session import ExamSession, ExamLog
from app.core.security import (
    create_session_poll_token,
    decode_token,
    get_current_admin,
    verify_session_poll_token,
)
from app.core.roles import is_admin_scope_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exams", tags=["Exam Admin Control"])
optional_bearer = HTTPBearer(auto_error=False)
SESSION_POLL_TOKEN_EXPIRES_MINUTES = 15


# ============== SCHEMAS ==============

class PauseResponse(BaseModel):
    """Response for pause/resume operations."""
    exam_id: int
    is_paused: bool
    paused_at: Optional[str] = None
    affected_sessions: int
    message: str


class ForceCompleteResponse(BaseModel):
    """Response for force complete operation."""
    exam_id: int
    completed_sessions: int
    total_active_sessions: int
    results_summary: dict
    message: str


class CleanupResponse(BaseModel):
    """Response for session cleanup operation."""
    exam_id: int
    deleted_count: int
    kept_count: int
    message: str


class StudentStatusItem(BaseModel):
    """Individual student status in an exam."""
    id: int
    name: str
    username: str
    status: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    score: Optional[float] = None


class StudentStatusResponse(BaseModel):
    """Real-time student participation status for exam management."""
    exam_id: int
    exam_title: str
    total_students: int
    active: int
    ready: int
    not_participating: int
    completed: int
    students: List[StudentStatusItem]
    last_updated: str


# ============== PAUSE/RESUME ENDPOINTS (Admin Only) ==============

@router.post("/{exam_id}/admin/pause-all")
async def pause_all_sessions(
    exam_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Pause all active sessions for an exam (admin only).
    Used for temporary interruptions (network issues, fire drill, etc).
    """
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = exam_result.scalar_one_or_none()

    if not exam:
        raise HTTPException(404, "Ujian tidak ditemukan")

    # Get all active sessions
    sessions_result = await db.execute(
        select(ExamSession).where(
            ExamSession.exam_id == exam_id,
            ExamSession.status == "in_progress",
            ExamSession.is_paused.is_(False)
        )
    )
    sessions = sessions_result.scalars().all()

    paused_count = 0
    for session in sessions:
        session.is_paused = True
        session.paused_at = datetime.now(timezone.utc)
        paused_count += 1

    await db.commit()

    return {
        "success": True,
        "message": f"⏸️ {paused_count} sesi berhasil di-pause",
        "paused_count": paused_count
    }


@router.post("/{exam_id}/admin/resume-all")
async def resume_all_sessions(
    exam_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Resume all paused sessions for an exam (admin only).
    Adjusts time to account for pause duration.
    """
    exam_result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = exam_result.scalar_one_or_none()

    if not exam:
        raise HTTPException(404, "Ujian tidak ditemukan")

    # Get all paused sessions
    sessions_result = await db.execute(
        select(ExamSession).where(
            ExamSession.exam_id == exam_id,
            ExamSession.is_paused == True
        )
    )
    sessions = sessions_result.scalars().all()

    resumed_count = 0
    now = datetime.now(timezone.utc)

    for session in sessions:
        if session.paused_at:
            # Calculate pause duration
            pause_duration = (now - session.paused_at).total_seconds()
            session.total_paused_seconds = (session.total_paused_seconds or 0) + int(pause_duration)

        session.is_paused = False
        session.paused_at = None
        resumed_count += 1

    await db.commit()

    return {
        "success": True,
        "message": f"▶️ {resumed_count} sesi berhasil dilanjutkan",
        "resumed_count": resumed_count
    }


# ============== EMERGENCY EXIT ENDPOINTS (Admin Only) ==============

@router.post("/sessions/{session_id}/emergency-exit")
async def enable_emergency_exit(
    session_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Enable emergency exit for a specific session.
    This allows the Flutter app to bypass kiosk mode and exit gracefully.

    Use case: Student's app is stuck, needs to restart/exit.
    """
    session_result = await db.execute(
        select(ExamSession).where(ExamSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "Sesi tidak ditemukan")

    if session.status not in ["in_progress", "created"]:
        raise HTTPException(400, "Sesi sudah selesai atau tidak aktif")

    # Enable emergency exit
    session.emergency_exit_allowed = True

    # Log this action
    log_entry = ExamLog(
        session_id=session_id,
        event_type="EMERGENCY_EXIT_ENABLED",
        event_data={
            "admin_id": current_user.id,
            "admin_username": current_user.username
        }
    )
    db.add(log_entry)

    await db.commit()

    logger.info(f"Emergency exit enabled for session {session_id} by admin {current_user.username}")

    return {
        "success": True,
        "message": "🚨 Emergency exit diaktifkan untuk sesi ini",
        "session_id": session_id,
        "emergency_exit_allowed": True
    }


@router.post("/sessions/{session_id}/terminate")
async def terminate_session(
    session_id: int,
    reason: Optional[str] = "Admin terminated",
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Force terminate a specific exam session (kick student).
    The student's app will be notified and forced to exit.

    Use case: Student caught cheating, need to revoke access immediately.
    """
    session_result = await db.execute(
        select(ExamSession).options(selectinload(ExamSession.user))
        .where(ExamSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "Sesi tidak ditemukan")

    if session.status not in ["in_progress", "created"]:
        raise HTTPException(400, "Sesi sudah selesai atau tidak aktif")

    # Calculate partial score before terminating
    from app.api.grading import recalculate_session_score
    try:
        score = await recalculate_session_score(session_id, db)
        session.score = score
    except Exception as e:
        logger.warning(f"Score calculation failed for terminated session {session_id}: {e}")
        session.score = 0

    # Terminate the session
    session.status = "terminated"
    session.terminated_by_admin = True
    session.emergency_exit_allowed = True  # Allow app to exit
    session.end_time = datetime.now(timezone.utc)

    # Log this action
    log_entry = ExamLog(
        session_id=session_id,
        event_type="SESSION_TERMINATED",
        event_data={
            "admin_id": current_user.id,
            "admin_username": current_user.username,
            "reason": reason,
            "student_name": session.user.full_name if session.user else "Unknown"
        }
    )
    db.add(log_entry)

    await db.commit()

    logger.warning(
        f"Session {session_id} terminated by admin {current_user.username}. "
        f"Reason: {reason}. Student: {session.user.full_name if session.user else 'Unknown'}"
    )

    return {
        "success": True,
        "message": f"🚫 Sesi {session_id} berhasil dihentikan paksa",
        "session_id": session_id,
        "status": "terminated",
        "score": float(session.score) if session.score else 0,
        "reason": reason
    }


@router.get("/sessions/{session_id}/status")
async def get_session_status(
    session_id: int,
    request: Request,
    poll_token: Optional[str] = Query(
        default=None,
        description="Short-lived signed poll token for anonymous-safe polling",
    ),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(optional_bearer),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current session status including admin control flags.
    Requires either valid Bearer JWT or signed short-lived poll token.
    """
    requester_user_id: Optional[int] = None
    requester_role: Optional[str] = None

    if credentials and credentials.credentials:
        token_data = decode_token(credentials.credentials, verify_exp=True)
        if token_data is None:
            raise HTTPException(401, "Token tidak valid atau sudah kadaluarsa")
        requester_user_id = token_data.user_id
    else:
        signed_token = poll_token or request.headers.get("X-Session-Poll-Token")
        if not signed_token:
            raise HTTPException(401, "Autentikasi diperlukan")
        requester_user_id = verify_session_poll_token(signed_token, session_id)
        if not requester_user_id:
            raise HTTPException(401, "Poll token tidak valid atau sudah kadaluarsa")
        requester_role = "student"

    requester_result = await db.execute(select(User).where(User.id == requester_user_id))
    requester = requester_result.scalar_one_or_none()
    if not requester or not requester.is_active:
        raise HTTPException(401, "Pengguna tidak valid atau tidak aktif")
    requester_role = requester_role or requester.role

    session_result = await db.execute(
        select(ExamSession)
        .options(selectinload(ExamSession.exam), selectinload(ExamSession.user))
        .where(ExamSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "Session not found")

    if is_admin_scope_role(requester_role):
        pass
    elif requester_role == "teacher":
        if not session.exam or session.exam.creator_id != requester.id:
            raise HTTPException(403, "Tidak memiliki akses ke sesi ini")
    elif requester.id != session.user_id:
        raise HTTPException(403, "Tidak memiliki akses ke sesi ini")

    refreshed_poll_token = create_session_poll_token(
        session_id=session.id,
        user_id=session.user_id,
        expires_minutes=SESSION_POLL_TOKEN_EXPIRES_MINUTES,
    )

    return {
        "session_id": session.id,
        "status": session.status,
        "emergency_exit_allowed": session.emergency_exit_allowed or False,
        "terminated_by_admin": session.terminated_by_admin or False,
        "is_paused": session.is_paused or False,
        "score": float(session.score) if session.score else None,
        "exam_title": session.exam.title if session.exam and not session.exam.is_deleted else session.archived_exam_title,
        "session_poll_token": refreshed_poll_token,
        "session_poll_token_expires_minutes": SESSION_POLL_TOKEN_EXPIRES_MINUTES,
    }


@router.post("/sessions/{session_id}/revoke-emergency-exit")
async def revoke_emergency_exit(
    session_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Revoke emergency exit permission for a session.
    Use if emergency exit was enabled by mistake.
    """
    session_result = await db.execute(
        select(ExamSession).where(ExamSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(404, "Sesi tidak ditemukan")

    session.emergency_exit_allowed = False

    # Log this action
    log_entry = ExamLog(
        session_id=session_id,
        event_type="EMERGENCY_EXIT_REVOKED",
        event_data={
            "admin_id": current_user.id,
            "admin_username": current_user.username
        }
    )
    db.add(log_entry)

    await db.commit()

    return {
        "success": True,
        "message": "Emergency exit dicabut untuk sesi ini",
        "session_id": session_id,
        "emergency_exit_allowed": False
    }
