"""Exam CRUD, publishing, token, and template/duplicate routes.

Public paths remain under ``/api/exams`` while this module keeps management
routes out of the large runtime/results module.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List
import logging
import secrets

import pytz
import sqlalchemy
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, noload, selectinload

from app.api.exams import (
    EXAM_AUDIT_FIELDS,
    _autofill_placeholder_options_for_publish,
    _collect_exam_update_changes,
    _enforce_developer_exam_visibility,
    _enforce_exam_owner_or_admin_access,
    _ensure_exam_participant_access,
    _exam_critical_metadata_changes,
    _is_exam_participant_role,
    _participant_has_exam_access,
    _publish_exam_monitor_event,
    _validate_questions_for_publish,
    log_admin_action,
)
from app.core.redis_pubsub import publish_message
from app.core.roles import ROLE_DEVELOPER
from app.core.security import get_current_teacher, get_current_user, is_pengawas_user
from app.database import get_db, get_db_read
from app.models.activity_log import UserActivityLog
from app.models.exam import Exam
from app.models.exam_template import ExamTemplate
from app.models.question import Question, QuestionOption
from app.models.session import ExamSession
from app.models.user import User
from app.schemas.exam import ExamCreate, ExamListResponse, ExamResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exams", tags=["Exam Management"])

@router.get("", response_model=ExamListResponse)
async def list_exams(
    skip: int = 0,
    limit: int = 10000,
    published_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_read)
):
    """List available exams.

    Access rules:
    - Participant roles (student + GuruPlus): Only published exams that match access policy
    - Teachers: Only their own exams
    - Pengawas (teacher+job_title pengawas): All published exams (monitoring lane)
    - Admins: All exams (published and drafts)
    """
    # Keep list endpoint lightweight: no heavy relationship loading.
    query = select(Exam).options(
        noload("*"),
        joinedload(Exam.creator).noload("*"),
        noload(Exam.questions),
        noload(Exam.sessions),
        noload(Exam.schedules),
    )

    # Always exclude soft-deleted exams
    query = query.where(Exam.is_deleted == False)

    if _is_exam_participant_role(current_user.role):
        # Participant roles only see published exams
        query = query.where(Exam.is_published == True)
    elif current_user.role == "teacher":
        query = query.where(Exam.creator.has(User.role != ROLE_DEVELOPER))
        if is_pengawas_user(current_user):
            # Pengawas is monitor-only: never expose drafts, but must see all published exams.
            query = query.where(Exam.is_published == True)
        else:
            # Teachers see ONLY their own exams (published and drafts)
            query = query.where(Exam.creator_id == current_user.id)
            if published_only:
                query = query.where(Exam.is_published == True)
    elif current_user.role in {"admin", ROLE_DEVELOPER}:
        if current_user.role == "admin":
            query = query.where(Exam.creator.has(User.role != ROLE_DEVELOPER))
        # Admin/developer sees everything
        if published_only:
            query = query.where(Exam.is_published == True)
        # If published_only=False, show all

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    raw_exams = result.scalars().all()

    # Batch question counts to avoid per-exam lazy loads.
    question_count_map: Dict[int, int] = {}
    exam_ids = [exam.id for exam in raw_exams]
    if exam_ids:
        count_rows = await db.execute(
            select(Question.exam_id, func.count(Question.id))
            .where(Question.exam_id.in_(exam_ids))
            .group_by(Question.exam_id)
        )
        question_count_map = {exam_id: total for exam_id, total in count_rows.all()}

    for exam in raw_exams:
        setattr(exam, "_question_count", int(question_count_map.get(exam.id, 0)))

    # Post-query filtering for participant roles based on class/student restriction.
    exams = []
    if _is_exam_participant_role(current_user.role):
        for exam in raw_exams:
            creator_role = getattr(getattr(exam, "creator", None), "role", None)
            if _participant_has_exam_access(
                exam,
                current_user,
                exam_creator_role=creator_role,
            ):
                exams.append(exam)
    else:
        exams = raw_exams

    # Count total with same role filters (exclude soft-deleted exams).
    if _is_exam_participant_role(current_user.role):
        total = len(exams)
    else:
        count_query = select(func.count(Exam.id)).where(Exam.is_deleted == False)
        if current_user.role == "teacher":
            if is_pengawas_user(current_user):
                count_query = count_query.where(Exam.creator.has(User.role != ROLE_DEVELOPER))
                count_query = count_query.where(Exam.is_published == True)
            else:
                count_query = count_query.where(Exam.creator_id == current_user.id)
                if published_only:
                    count_query = count_query.where(Exam.is_published == True)
        elif current_user.role in {"admin", ROLE_DEVELOPER}:
            if current_user.role == "admin":
                count_query = count_query.where(Exam.creator.has(User.role != ROLE_DEVELOPER))
            if published_only:
                count_query = count_query.where(Exam.is_published == True)

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

    return ExamListResponse(
        exams=[ExamResponse.from_orm_with_wib(exam) for exam in exams],
        total=total
    )


@router.get("/{exam_id}", response_model=ExamResponse)
async def get_exam(
    exam_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_read)
):
    """Get exam details."""
    question_count_expr = (
        select(func.count(Question.id))
        .where(Question.exam_id == Exam.id)
        .scalar_subquery()
    )

    result = await db.execute(
        select(
            Exam.id,
            Exam.title,
            Exam.description,
            Exam.creator_id,
            Exam.duration_minutes,
            Exam.start_time,
            Exam.end_time,
            Exam.passing_score,
            Exam.max_attempts,
            Exam.shuffle_questions,
            Exam.shuffle_options,
            Exam.show_results,
            Exam.allow_review,
            Exam.is_published,
            Exam.access_token,
            Exam.subject,
            Exam.exam_type,
            Exam.academic_year,
            Exam.show_teacher_name,
            Exam.builder_settings,
            Exam.allowed_classes,
            Exam.allowed_students,
            Exam.created_at,
            User.full_name.label("teacher_name"),
            User.role.label("creator_role"),
            func.coalesce(question_count_expr, 0).label("question_count"),
        )
        .join(User, User.id == Exam.creator_id)
        .where(Exam.id == exam_id, Exam.is_deleted == False)
    )
    exam = result.one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    if _is_exam_participant_role(current_user.role):
        if not exam.is_published:
            raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")
        _ensure_exam_participant_access(
            SimpleNamespace(
                allowed_students=exam.allowed_students,
                allowed_classes=exam.allowed_classes,
            ),
            current_user,
            exam_creator_role=exam.creator_role,
        )
    else:
        _enforce_developer_exam_visibility(current_user, exam.creator_role)

    # 🆕 FIX #4: Standardized permission check (admin bypass)
    if (
        exam.creator_id != current_user.id
        and not current_user.is_admin
        and not is_pengawas_user(current_user)
    ):
        raise HTTPException(status_code=403, detail="Tidak memiliki akses ke ujian ini")

    def format_wib(dt):
        if dt is None:
            return ""
        if dt.tzinfo is None:
            return dt.strftime('%d %B %Y %H:%M WIB')
        wib = pytz.timezone('Asia/Jakarta')
        return dt.astimezone(wib).strftime('%d %B %Y %H:%M WIB')

    return ExamResponse(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        creator_id=exam.creator_id,
        duration_minutes=exam.duration_minutes,
        start_time=exam.start_time,
        end_time=exam.end_time,
        start_time_wib=format_wib(exam.start_time),
        end_time_wib=format_wib(exam.end_time),
        passing_score=exam.passing_score,
        max_attempts=exam.max_attempts,
        shuffle_questions=exam.shuffle_questions,
        shuffle_options=exam.shuffle_options,
        show_results=exam.show_results,
        allow_review=exam.allow_review,
        is_published=exam.is_published,
        access_token=exam.access_token,
        subject=exam.subject,
        exam_type=exam.exam_type,
        academic_year=exam.academic_year,
        show_teacher_name=exam.show_teacher_name if exam.show_teacher_name is not None else True,
        builder_settings=exam.builder_settings or {},
        teacher_name=exam.teacher_name,
        allowed_classes=exam.allowed_classes,
        allowed_students=exam.allowed_students,
        question_count=int(exam.question_count or 0),
        created_at=exam.created_at,
    )


# ============== TEACHER EXAM MANAGEMENT ==============

@router.post("", response_model=ExamResponse, status_code=201)
async def create_exam(
    exam_data: ExamCreate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Create a new exam (Teacher/Admin only)."""
    # 1. Validate times
    if exam_data.end_time <= exam_data.start_time:
        raise HTTPException(status_code=400, detail="Waktu selesai harus setelah waktu mulai")

    # 2. Create Exam with Unique Token Retry
    for _ in range(5): # Retry up to 5 times
        try:
            token = secrets.token_hex(3).upper()

            new_exam = Exam(
                title=exam_data.title,
                description=exam_data.description,
                creator_id=current_user.id,
                duration_minutes=exam_data.duration_minutes,
                start_time=exam_data.start_time,
                end_time=exam_data.end_time,
                passing_score=exam_data.passing_score,
                max_attempts=exam_data.max_attempts,
                shuffle_questions=exam_data.shuffle_questions,
                shuffle_options=exam_data.shuffle_options,
                show_results=exam_data.show_results,
                allow_review=exam_data.allow_review,
                is_published=exam_data.is_published,
                subject=exam_data.subject,
                exam_type=exam_data.exam_type,
                academic_year=exam_data.academic_year,
                show_teacher_name=exam_data.show_teacher_name,
                builder_settings=exam_data.builder_settings or {},
                allowed_classes=exam_data.allowed_classes,
                allowed_students=exam_data.allowed_students,
                # Secure Token Generation
                access_token=token,
                seb_config_key=secrets.token_urlsafe(32),
                seb_browser_exam_key=secrets.token_urlsafe(32)
            )

            db.add(new_exam)
            await db.commit()
            await db.refresh(new_exam)

            return ExamResponse.from_orm_with_wib(new_exam)

        except sqlalchemy.exc.IntegrityError:
            await db.rollback()
            continue # Try next token

    raise HTTPException(status_code=500, detail="Gagal generate token ujian yang unik. Silakan coba lagi.")


@router.put("/{exam_id}", response_model=ExamResponse)
async def update_exam(
    exam_id: int,
    exam_data: ExamCreate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Update exam details."""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    # Check permissions
    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        exam.creator_id,
    )

    # Update fields
    if exam_data.end_time <= exam_data.start_time:
        raise HTTPException(status_code=400, detail="Waktu selesai harus setelah waktu mulai")

    original_values = {field: getattr(exam, field) for field in EXAM_AUDIT_FIELDS}
    critical_changes = _exam_critical_metadata_changes(exam, exam_data)
    if critical_changes:
        session_count_result = await db.execute(
            select(func.count(ExamSession.id)).where(ExamSession.exam_id == exam_id)
        )
        session_count = int(session_count_result.scalar() or 0)
        if session_count > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Ujian sudah memiliki sesi peserta. Perubahan jadwal atau target peserta "
                    "dikunci agar hasil historis tidak berubah konteks. Buat ujian/susulan baru "
                    "atau hubungi developer untuk recovery terkontrol."
                ),
            )

    exam.title = exam_data.title
    exam.description = exam_data.description
    exam.duration_minutes = exam_data.duration_minutes
    exam.start_time = exam_data.start_time
    exam.end_time = exam_data.end_time
    exam.passing_score = exam_data.passing_score
    exam.max_attempts = exam_data.max_attempts
    exam.shuffle_questions = exam_data.shuffle_questions
    exam.shuffle_options = exam_data.shuffle_options
    exam.show_results = exam_data.show_results
    exam.allow_review = exam_data.allow_review
    exam.is_published = exam_data.is_published
    exam.subject = exam_data.subject
    exam.exam_type = exam_data.exam_type
    exam.academic_year = exam_data.academic_year
    exam.show_teacher_name = exam_data.show_teacher_name
    exam.builder_settings = exam_data.builder_settings or {}
    exam.allowed_classes = exam_data.allowed_classes
    exam.allowed_students = exam_data.allowed_students

    update_changes = _collect_exam_update_changes(original_values, exam_data)

    await db.commit()
    # 🆕 FIX: Expire cache and force fresh read from DB
    db.expire(exam)
    await db.refresh(exam)

    if update_changes:
        db.add(
            UserActivityLog(
                user_id=current_user.id,
                event_type="exam_updated",
                event_data={
                    "actor_username": current_user.username,
                    "actor_role": current_user.role,
                    "target_exam_id": exam_id,
                    "target_exam_title": exam.title,
                    "critical_changes": critical_changes,
                    "changes": update_changes,
                },
            )
        )
        await db.commit()

    # Log admin action if admin editing other teacher's exam
    if current_user.is_admin and exam.creator_id != current_user.id:
        # Convert exam_data to dict and handle JSON serialization
        def json_serializable(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, (int, float, str, bool, type(None))):
                return obj
            elif isinstance(obj, (list, tuple)):
                return [json_serializable(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: json_serializable(v) for k, v in obj.items()}
            else:
                return str(obj)

        changes_dict = exam_data.dict()
        changes_dict = json_serializable(changes_dict)

        await log_admin_action(
            db, current_user, "edit", "exam", exam_id, exam.title,
            {"original_creator_id": exam.creator_id, "changes": changes_dict}
        )

    return ExamResponse.from_orm_with_wib(exam)


@router.delete("/{exam_id}", status_code=204)
async def delete_exam(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Soft delete an exam."""
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        exam.creator_id,
    )

    # Archive metadata for all sessions before soft delete
    # This preserves what exam the student took even if the exam definition is deleted
    sessions_result = await db.execute(
        select(ExamSession).where(ExamSession.exam_id == exam_id)
    )
    sessions = sessions_result.scalars().all()

    for session in sessions:
        # Check if columns exist (assuming they were added in models)
        # If not, this is a safety check. Based on audit, we assume implementation needed.
        # Ideally, ExamSession model should have these columns.
        if hasattr(session, 'archived_exam_title'):
            session.archived_exam_title = exam.title
            session.archived_exam_subject = exam.subject
            session.archived_exam_type = exam.exam_type

    # Soft delete
    exam.is_deleted = True
    # exam.deleted_at = datetime.now(timezone.utc) # Uncomment if column exists
    await db.commit()

    # Log admin action if admin deleting other teacher's exam
    if current_user.is_admin and exam.creator_id != current_user.id:
        await log_admin_action(
            db, current_user, "delete", "exam", exam_id, exam.title,
            {"original_creator_id": exam.creator_id, "soft_delete": True}
        )

    return Response(status_code=204)


@router.post("/{exam_id}/publish")
async def publish_exam(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Publish an exam to make it visible to students."""
    if is_pengawas_user(current_user):
        raise HTTPException(
            status_code=403,
            detail="Pengawas tidak diizinkan publish ujian. Hanya guru pembuat atau admin.",
        )

    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        exam.creator_id,
    )

    # Auto-fill placeholder options when teacher only sets keys (super-permissive authoring mode)
    await _autofill_placeholder_options_for_publish(exam_id, db)

    # Validate after normalization
    await _validate_questions_for_publish(exam_id, db)

    exam.is_published = True
    await db.commit()

    return {"message": "Ujian berhasil dipublikasikan", "is_published": True}


@router.patch("/{exam_id}/publish")
async def toggle_publish_exam(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Toggle exam publish status (publish/unpublish)."""
    from app.core.redis_pubsub import publish_message
    from app.models.session import ExamSession

    if is_pengawas_user(current_user):
        raise HTTPException(
            status_code=403,
            detail="Pengawas tidak diizinkan publish atau unpublish ujian.",
        )

    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        exam.creator_id,
    )

    was_published = exam.is_published

    # Validate before transitioning draft -> published
    if not was_published:
        await _autofill_placeholder_options_for_publish(exam_id, db)
        await _validate_questions_for_publish(exam_id, db)

    # Toggle publish status
    exam.is_published = not exam.is_published
    await db.commit()

    # If exam was just UNPUBLISHED (cancelled), notify all active students
    if was_published and not exam.is_published:
        # Get all active sessions for this exam
        active_sessions = await db.execute(
            select(ExamSession)
            .where(
                ExamSession.exam_id == exam_id,
                ExamSession.status.in_(['in_progress', 'started', 'active'])
            )
        )
        sessions = active_sessions.scalars().all()
        target_user_ids = [int(s.user_id) for s in sessions]
        # Close read transaction before Redis/network operations.
        await db.commit()

        # Get teacher/admin name for notification
        cancelled_by = current_user.full_name or current_user.username

        # Send cancellation notification to each active student
        for target_user_id in target_user_ids:
            try:
                await publish_message(f"exam_student_{exam_id}_{target_user_id}", {
                    "type": "exam_cancelled",
                    "reason": "Ujian telah dibatalkan atau ditunda oleh pengawas",
                    "cancelled_by": cancelled_by,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            except Exception as e:
                logger.error(
                    "Failed to notify student %s: %s",
                    target_user_id,
                    str(e),
                    exc_info=True,
                )

        # Also broadcast to exam monitor channel
        try:
            await _publish_exam_monitor_event(exam_id, {
                "type": "exam_unpublished",
                "exam_id": exam_id,
                "cancelled_by": cancelled_by,
                "active_students_notified": len(sessions),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        except Exception as exc:
            logger.warning(
                "Failed to broadcast exam_unpublished monitor event for exam_id=%s: %s",
                exam_id,
                str(exc),
                exc_info=True,
            )

        # CRITICAL: Delete non-submitted sessions so students can rejoin when republished
        # Only keep submitted/completed sessions (actual exam attempts that count)
        from sqlalchemy import delete
        delete_result = await db.execute(
            delete(ExamSession)
            .where(
                ExamSession.exam_id == exam_id,
                ~ExamSession.status.in_(['submitted', 'completed'])
            )
        )
        await db.commit()

        logger.info(
            "Exam %s unpublished: deleted %s non-submitted sessions",
            exam_id,
            delete_result.rowcount,
        )

    action = "dipublikasikan" if exam.is_published else "dibatalkan publikasinya"
    return {
        "message": f"Ujian berhasil {action}",
        "is_published": exam.is_published
    }

@router.post("/{exam_id}/regenerate-token", response_model=ExamResponse)
async def regenerate_exam_token(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Regenerate exam access token (teacher/admin only)."""
    if is_pengawas_user(current_user):
        raise HTTPException(
            status_code=403,
            detail="Pengawas tidak diizinkan mengganti token ujian.",
        )

    result = await db.execute(
        select(Exam)
        .options(selectinload(Exam.questions))
        .where(Exam.id == exam_id)
    )
    exam = result.scalar_one_or_none()

    if not exam:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        exam.creator_id,
    )

    # Generate new token
    allowed_chars = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'

    for _ in range(10):
        new_token = ''.join(secrets.choice(allowed_chars) for _ in range(6))
        existing = await db.execute(select(Exam).where(Exam.access_token == new_token))
        if not existing.scalar_one_or_none():
            break
    else:
        raise HTTPException(status_code=500, detail="Gagal generate token baru")

    exam.access_token = new_token
    exam.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(exam)

    return ExamResponse.from_orm_with_wib(exam)

@router.post("/from-template", response_model=ExamResponse)
async def create_exam_from_template(
    template_id: int,
    start_time: datetime,
    end_time: datetime,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Create a new exam from a template."""
    # Fetch template
    result = await db.execute(select(ExamTemplate).where(ExamTemplate.id == template_id))
    template = result.scalar_one_or_none()

    if not template:
        raise HTTPException(404, "Template not found")

    data = template.template_data

    # Create Exam
    new_exam = Exam(
        title=data.get('title', 'Untitled Exam'),
        description=data.get('description'),
        creator_id=current_user.id,
        duration_minutes=data.get('duration_minutes', 60),
        start_time=start_time,
        end_time=end_time,
        passing_score=data.get('passing_score', 0),
        max_attempts=data.get('max_attempts', 1),
        shuffle_questions=data.get('shuffle_questions', False),
        shuffle_options=data.get('shuffle_options', False),
        show_results=data.get('show_results', False),  # FIX: Default to False to match checkbox default
        allow_review=data.get('allow_review', False),
        builder_settings=data.get('builder_settings', {}),
        seb_config_key=secrets.token_urlsafe(32),
        seb_browser_exam_key=secrets.token_urlsafe(32),
        is_published=False,
        access_token=secrets.token_hex(3).upper(),  # Temporary basic token
        allowed_classes=None
    )

    db.add(new_exam)
    await db.commit()
    await db.refresh(new_exam)

    # Copy questions (simplified logic, assumes template_data has questions structure)
    # Ideally templates should store question prototypes.
    # For now, if template_data has 'questions', we implement basic copying.
    # Implementation deferred/simplified for brevity as templates usually need robust structure.

    return ExamResponse.from_orm_with_wib(new_exam)


@router.post("/{exam_id}/duplicate", response_model=ExamResponse)
async def duplicate_exam(
    exam_id: int,
    include_questions: bool = True,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Duplicate an existing exam."""
    # Fetch original
    result = await db.execute(
        select(Exam)
        .options(selectinload(Exam.questions).selectinload(Question.options))
        .where(Exam.id == exam_id)
    )
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(404, "Original exam not found")
    await _enforce_exam_owner_or_admin_access(
        db,
        current_user,
        original.creator_id,
    )

    # Create Copy
    new_exam = Exam(
        title=f"{original.title} (Copy)",
        description=original.description,
        creator_id=current_user.id,
        duration_minutes=original.duration_minutes,
        start_time=original.start_time,
        end_time=original.end_time,
        passing_score=original.passing_score,
        max_attempts=original.max_attempts,
        shuffle_questions=original.shuffle_questions,
        shuffle_options=original.shuffle_options,
        show_results=original.show_results,
        allow_review=original.allow_review,
        builder_settings=original.builder_settings or {},
        seb_config_key=secrets.token_urlsafe(32),
        seb_browser_exam_key=secrets.token_urlsafe(32),
        is_published=False,
        access_token=secrets.token_hex(3).upper(),
        allowed_classes=original.allowed_classes
    )

    db.add(new_exam)
    await db.commit()
    await db.refresh(new_exam)

    # Duplicate Questions
    if include_questions and original.questions:
        for q in original.questions:
            new_q = Question(
                exam_id=new_exam.id,
                question_text=q.question_text,
                question_type=q.question_type,
                question_subtype=q.question_subtype,
                pgk_type=q.pgk_type,
                stimulus=q.stimulus,
                question_settings=q.question_settings,
                points=q.points,
                order_index=q.order_index,
                image_url=q.image_url,
                video_url=q.video_url,
                audio_url=q.audio_url
            )
            db.add(new_q)
            await db.flush() # Get ID

            # Duplicate Options
            for opt in q.options:
                new_opt = QuestionOption(
                    question_id=new_q.id,
                    option_text=opt.option_text,
                    is_correct=opt.is_correct,
                    order_index=opt.order_index,
                    option_group=opt.option_group,
                    pair_id=opt.pair_id,
                    option_metadata=opt.option_metadata
                )
                db.add(new_opt)

        await db.commit()

    return ExamResponse.from_orm_with_wib(new_exam)
