"""
Scheduled Publication API endpoints.
Auto-publish/unpublish scheduling for exams.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List

from app.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.models.scheduled import ScheduledPublication
from app.schemas.scheduled import ScheduleCreate, ScheduleResponse
from app.core.security import get_current_teacher, get_current_active_admin
from app.core.roles import is_admin_scope_role

router = APIRouter(prefix="/api/scheduled", tags=["Scheduled Publishing"])


@router.post("/exams/{exam_id}/schedule", response_model=ScheduleResponse, status_code=201)
async def schedule_exam_publication(
    exam_id: int,
    schedule_data: ScheduleCreate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    Schedule automatic publish/unpublish of exam.

    **Requirements:**
    - publish_at: Future datetime when exam will be auto-published
    - unpublish_at: (Optional) Future datetime when exam will be auto-unpublished

    **Authorization:**
    - Teacher can only schedule their own exams
    - Admin can schedule any exam
    """
    # Validate exam exists
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(404, "Ujian tidak ditemukan")

    # Authorization check
    if exam.creator_id != current_user.id and not is_admin_scope_role(current_user.role):
        raise HTTPException(403, "Tidak memiliki akses untuk menjadwalkan ujian ini")

    # Check for existing pending schedule
    existing = await db.execute(
        select(ScheduledPublication)
        .where(
            ScheduledPublication.exam_id == exam_id,
            ScheduledPublication.status == 'pending'
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Ujian sudah memiliki jadwal pending. Batalkan terlebih dahulu.")

    # Create schedule
    schedule = ScheduledPublication(
        exam_id=exam_id,
        publish_at=schedule_data.publish_at,
        unpublish_at=schedule_data.unpublish_at,
        created_by=current_user.id,
        status='pending'
    )

    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)

    return schedule


@router.get("/exams/{exam_id}/schedules", response_model=List[ScheduleResponse])
async def get_exam_schedules(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Get all schedules for an exam (past and present)."""
    # Check exam access
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(404, "Ujian tidak ditemukan")

    if exam.creator_id != current_user.id and not is_admin_scope_role(current_user.role):
        raise HTTPException(403, "Tidak memiliki akses")

    # Get schedules
    schedules_result = await db.execute(
        select(ScheduledPublication)
        .where(ScheduledPublication.exam_id == exam_id)
        .order_by(ScheduledPublication.created_at.desc())
    )
    schedules = schedules_result.scalars().all()

    return schedules


@router.delete("/schedules/{schedule_id}")
async def cancel_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Cancel a pending schedule."""
    result = await db.execute(
        select(ScheduledPublication).where(ScheduledPublication.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(404, "Jadwal tidak ditemukan")

    if schedule.status != 'pending':
        raise HTTPException(400, f"Tidak dapat membatalkan jadwal dengan status: {schedule.status}")

    # Authorization check
    if schedule.created_by != current_user.id and not is_admin_scope_role(current_user.role):
        raise HTTPException(403, "Tidak memiliki akses untuk membatalkan jadwal ini")

    schedule.status = 'cancelled'
    await db.commit()

    return {"message": "Jadwal berhasil dibatalkan"}


@router.get("/schedules/upcoming", response_model=List[ScheduleResponse])
async def get_upcoming_schedules(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get upcoming pending schedules (admin only)."""
    result = await db.execute(
        select(ScheduledPublication)
        .where(ScheduledPublication.status == 'pending')
        .order_by(ScheduledPublication.publish_at.asc())
        .limit(limit)
    )
    schedules = result.scalars().all()

    return schedules


@router.get("/schedules/stats")
async def get_schedule_stats(
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get scheduling statistics (admin only)."""
    # Count by status
    stats = {}
    for status in ['pending', 'published', 'unpublished', 'cancelled']:
        result = await db.execute(
            select(func.count(ScheduledPublication.id))
            .where(ScheduledPublication.status == status)
        )
        stats[status] = result.scalar() or 0

    return {
        "total": sum(stats.values()),
        "by_status": stats
    }
