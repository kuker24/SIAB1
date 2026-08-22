"""Exam pause/resume control routes.

Separated from the large exam routes module while keeping public paths under
``/api/exams`` unchanged.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exam_access_policy import (
    ensure_exam_participant_access as _ensure_exam_participant_access,
    is_exam_participant_role as _is_exam_participant_role,
)
from app.core.roles import is_developer_exam_hidden_for_viewer
from app.core.redis_pubsub import get_session_data, publish_message, store_session_data
from app.core.security import get_current_teacher, get_current_user, is_pengawas_user
from app.database import get_db
from app.models.exam import Exam
from app.models.session import ExamSession
from app.models.user import User

router = APIRouter(prefix="/api/exams", tags=["Exam Pause Control"])


class PauseResponse(BaseModel):
    """Response for pause/resume operations."""

    exam_id: int
    is_paused: bool
    paused_at: Optional[str] = None
    affected_sessions: int
    message: str


async def _get_exam_creator_role(db: AsyncSession, creator_id: Optional[int]) -> Optional[str]:
    if not creator_id:
        return None

    creator_role_result = await db.execute(select(User.role).where(User.id == creator_id))
    return creator_role_result.scalar_one_or_none()


def _raise_hidden_exam_error() -> None:
    raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")


def _enforce_developer_exam_visibility(
    current_user: User,
    exam_creator_role: Optional[str],
) -> None:
    if is_developer_exam_hidden_for_viewer(current_user.role, exam_creator_role):
        _raise_hidden_exam_error()


async def _enforce_exam_owner_or_admin_access(
    db: AsyncSession,
    current_user: User,
    exam_creator_id: int,
    *,
    allow_pengawas: bool = False,
) -> str:
    creator_role = await _get_exam_creator_role(db, exam_creator_id)
    _enforce_developer_exam_visibility(current_user, creator_role)

    if exam_creator_id == current_user.id:
        return str(creator_role or "")

    if bool(getattr(current_user, "is_admin", False)):
        return str(creator_role or "")

    if allow_pengawas and is_pengawas_user(current_user):
        return str(creator_role or "")

    raise HTTPException(status_code=403, detail="Tidak memiliki akses")


@router.post("/{exam_id}/pause-all", response_model=PauseResponse)
async def pause_exam_globally(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    """Pause exam for all active students."""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(404, "Ujian tidak ditemukan")

    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        exam.creator_id,
        allow_pengawas=True,
    )

    if exam.is_globally_paused:
        raise HTTPException(400, "Ujian sudah dalam status pause")

    now = datetime.now(timezone.utc)
    exam.is_globally_paused = True
    exam.globally_paused_at = now
    exam.globally_paused_by = current_user.id

    sessions_result = await db.execute(
        select(ExamSession)
        .where(ExamSession.exam_id == exam_id)
        .where(ExamSession.status == "in_progress")
    )
    active_sessions = sessions_result.scalars().all()

    for session in active_sessions:
        session.is_paused = True
        session.paused_at = now

    await db.commit()

    await publish_message("exam_control", {
        "type": "exam_paused",
        "exam_id": exam_id,
        "paused_at": now.isoformat(),
        "paused_by": current_user.full_name or current_user.username,
        "message": "Ujian telah di-pause oleh pengawas",
    })

    for session in active_sessions:
        await publish_message(f"exam_student_{exam_id}_{session.user_id}", {
            "type": "exam_paused",
            "exam_id": exam_id,
            "paused_at": now.isoformat(),
            "paused_by": current_user.full_name or current_user.username,
            "message": "Ujian telah di-pause oleh pengawas",
        })

    from app.api.activity import log_activity

    await log_activity(
        db=db,
        user_id=current_user.id,
        event_type="admin_pause_exam",
        event_data={
            "exam_id": exam_id,
            "exam_title": exam.title,
            "affected_sessions": len(active_sessions),
            "paused_at": now.isoformat(),
        },
    )
    await db.commit()

    return PauseResponse(
        exam_id=exam_id,
        is_paused=True,
        paused_at=now.isoformat(),
        affected_sessions=len(active_sessions),
        message=f"Ujian berhasil di-pause. {len(active_sessions)} sesi terpengaruh.",
    )


@router.post("/{exam_id}/resume-all", response_model=PauseResponse)
async def resume_exam_globally(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db),
):
    """Resume exam for all paused students."""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(404, "Ujian tidak ditemukan")

    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        exam.creator_id,
        allow_pengawas=True,
    )

    if not exam.is_globally_paused:
        raise HTTPException(400, "Ujian tidak dalam status pause")

    now = datetime.now(timezone.utc)
    pause_duration = int((now - exam.globally_paused_at).total_seconds()) if exam.globally_paused_at else 0

    exam.is_globally_paused = False
    exam.globally_paused_at = None

    sessions_result = await db.execute(
        select(ExamSession)
        .where(ExamSession.exam_id == exam_id)
        .where(ExamSession.is_paused == True)
    )
    paused_sessions = sessions_result.scalars().all()
    paused_session_ids: List[int] = []
    paused_session_user_map: Dict[int, int] = {}
    paused_session_total_map: Dict[int, int] = {}

    for session in paused_sessions:
        session.is_paused = False
        session.total_paused_seconds = (session.total_paused_seconds or 0) + pause_duration
        session.paused_at = None
        paused_session_ids.append(int(session.id))
        paused_session_user_map[int(session.id)] = int(session.user_id)
        paused_session_total_map[int(session.id)] = int(session.total_paused_seconds or 0)

    await db.commit()

    for paused_session_id in paused_session_ids:
        redis_data = await get_session_data(paused_session_id)
        if redis_data:
            redis_data["total_paused_seconds"] = paused_session_total_map.get(paused_session_id, 0)
            await store_session_data(paused_session_id, redis_data)

    await publish_message("exam_control", {
        "type": "exam_resumed",
        "exam_id": exam_id,
        "resumed_at": now.isoformat(),
        "pause_duration_seconds": pause_duration,
        "message": "Ujian dilanjutkan. Timer Anda sudah disesuaikan.",
    })

    for paused_session_id in paused_session_ids:
        target_user_id = paused_session_user_map.get(paused_session_id)
        if target_user_id is None:
            continue
        await publish_message(f"exam_student_{exam_id}_{target_user_id}", {
            "type": "exam_resumed",
            "exam_id": exam_id,
            "resumed_at": now.isoformat(),
            "pause_duration_seconds": pause_duration,
            "message": "Ujian dilanjutkan. Timer Anda sudah disesuaikan.",
        })

    from app.api.activity import log_activity

    await log_activity(
        db=db,
        user_id=current_user.id,
        event_type="admin_resume_exam",
        event_data={
            "exam_id": exam_id,
            "exam_title": exam.title,
            "affected_sessions": len(paused_sessions),
            "pause_duration_seconds": pause_duration,
        },
    )
    await db.commit()

    return PauseResponse(
        exam_id=exam_id,
        is_paused=False,
        paused_at=None,
        affected_sessions=len(paused_sessions),
        message=f"Ujian dilanjutkan. {len(paused_sessions)} sesi resumed. Pause duration: {pause_duration}s",
    )


@router.get("/{exam_id}/pause-status")
async def get_pause_status(
    exam_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current pause status of an exam."""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(404, "Ujian tidak ditemukan")

    if _is_exam_participant_role(current_user.role):
        creator_role = await _get_exam_creator_role(db, exam.creator_id)
        _ensure_exam_participant_access(
            exam,
            current_user,
            exam_creator_role=creator_role,
        )
    else:
        await _enforce_exam_owner_or_admin_access(
            db,
            current_user,
            exam.creator_id,
            allow_pengawas=True,
        )

    pause_duration = 0
    if exam.is_globally_paused and exam.globally_paused_at:
        pause_duration = int((datetime.now(timezone.utc) - exam.globally_paused_at).total_seconds())

    return {
        "exam_id": exam_id,
        "is_paused": exam.is_globally_paused,
        "paused_at": exam.globally_paused_at.isoformat() if exam.globally_paused_at else None,
        "current_pause_duration": pause_duration,
    }
