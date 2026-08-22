"""
Dashboard statistics API endpoints.
"""
import time
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.database import get_db_read
from app.models.user import User
from app.models.exam import Exam
from app.models.session import ExamSession
from app.core.security import get_current_user
from app.core.roles import (
    ROLE_DEVELOPER,
    is_admin_scope_role,
    is_developer_role,
    is_participant_role,
)

router = APIRouter(prefix="/api/stats", tags=["Statistics"])

DASHBOARD_CACHE_TTL_SECONDS = 15
_dashboard_cache: Dict[str, Dict[str, Any]] = {}


def _get_dashboard_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    cache_entry = _dashboard_cache.get(cache_key)
    if not cache_entry:
        return None
    if time.monotonic() >= cache_entry["expires_at"]:
        _dashboard_cache.pop(cache_key, None)
        return None
    return cache_entry["payload"]


def _set_dashboard_cache(cache_key: str, payload: Dict[str, Any]) -> None:
    _dashboard_cache[cache_key] = {
        "expires_at": time.monotonic() + DASHBOARD_CACHE_TTL_SECONDS,
        "payload": payload
    }


@router.get("/dashboard")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_read)
):
    """Get dashboard statistics."""
    cache_key = f"{current_user.role}:{current_user.id}"
    cached_payload = _get_dashboard_cache(cache_key)
    if cached_payload is not None:
        return cached_payload

    now = datetime.now(timezone.utc)

    # Restrict exam scope by role to avoid loading global data for teachers.
    exam_filters = [Exam.is_deleted == False]
    if current_user.role == "teacher":
        exam_filters.append(Exam.creator_id == current_user.id)
    elif is_admin_scope_role(current_user.role):
        if not is_developer_role(current_user.role):
            exam_filters.append(Exam.creator.has(User.role != ROLE_DEVELOPER))
    elif is_participant_role(current_user.role):
        exam_filters.append(Exam.is_published == True)

    # Total users (admin only)
    total_users = 0
    if is_admin_scope_role(current_user.role):
        result = await db.execute(select(func.count(User.id)))
        total_users = result.scalar() or 0

    # Aggregate exam counts in a single query.
    result = await db.execute(
        select(
            func.count(Exam.id).label("total_exams"),
            func.count(Exam.id).filter(Exam.is_published == True).label("published_exams"),
            func.count(Exam.id).filter(Exam.is_published == False).label("draft_exams"),
            func.count(Exam.id).filter(
                and_(
                    Exam.is_published == True,
                    Exam.start_time > now
                )
            ).label("upcoming_exams")
        ).where(*exam_filters)
    )
    exam_counts = result.one()
    total_exams = exam_counts.total_exams or 0
    published_exams = exam_counts.published_exams or 0
    draft_exams = exam_counts.draft_exams or 0
    upcoming_exams = exam_counts.upcoming_exams or 0

    # Students should not see draft count even if backend includes fallback values.
    if is_participant_role(current_user.role):
        draft_exams = 0

    # Active sessions (in progress) within the role-scoped exam set.
    result = await db.execute(
        select(func.count(ExamSession.id))
        .select_from(ExamSession)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(*exam_filters, ExamSession.status == "in_progress", Exam.is_published == True)
    )
    active_sessions = result.scalar() or 0

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_start = today_start + timedelta(days=1)
    result = await db.execute(
        select(func.count(ExamSession.id))
        .select_from(ExamSession)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(
            *exam_filters,
            ExamSession.status == "submitted",
            ExamSession.end_time >= today_start,
            ExamSession.end_time < tomorrow_start
        )
    )
    completed_today = result.scalar() or 0

    # Recent exams (for admin/teacher dashboards)
    recent_exams = []
    if current_user.role == "teacher" or is_admin_scope_role(current_user.role):
        result = await db.execute(
            select(
                Exam.id,
                Exam.title,
                Exam.duration_minutes,
                Exam.start_time,
                Exam.end_time,
                Exam.is_published,
            )
            .where(*exam_filters)
            .order_by(Exam.created_at.desc())
            .limit(5)
        )
        exams = result.all()
        for exam in exams:
            recent_exams.append({
                "id": exam.id,
                "title": exam.title,
                "duration_minutes": exam.duration_minutes,
                "start_time": exam.start_time.isoformat() if exam.start_time else None,
                "end_time": exam.end_time.isoformat() if exam.end_time else None,
                "is_published": exam.is_published
            })

    payload = {
        "total_users": total_users,
        "total_exams": total_exams,
        "published_exams": published_exams,
        "draft_exams": draft_exams,
        "active_sessions": active_sessions,
        "completed_today": completed_today,
        "upcoming_exams": upcoming_exams,
        "recent_exams": recent_exams
    }
    _set_dashboard_cache(cache_key, payload)
    return payload
