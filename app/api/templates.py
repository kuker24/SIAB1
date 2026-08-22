"""
Exam Templates API endpoints.
Full CRUD for exam templates.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
import secrets

from app.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.models.exam_template import ExamTemplate
from app.schemas.template import (
    TemplateCreate, TemplateUpdate, TemplateResponse,
    TemplateListResponse, ExamFromTemplateCreate
)
from app.schemas.exam import ExamResponse
from app.core.security import get_current_teacher
from app.core.roles import (
    ROLE_DEVELOPER,
    is_admin_scope_role,
    is_developer_exam_hidden_for_viewer,
    is_developer_role,
)

router = APIRouter(prefix="/api/templates", tags=["Exam Templates"])


@router.get("/", response_model=TemplateListResponse)
async def list_templates(
    public_only: bool = Query(False, description="Show only public templates"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    List available exam templates.

    - Teachers see: public templates + their own private templates
    - Admins see: all templates
    """
    query = select(ExamTemplate).join(User, User.id == ExamTemplate.creator_id, isouter=True)

    if current_user.role == "teacher":
        # Teachers: public OR owned by them
        query = query.where(
            or_(
                ExamTemplate.is_public == True,
                ExamTemplate.creator_id == current_user.id
            )
        )
        query = query.where(or_(User.role.is_(None), User.role != ROLE_DEVELOPER))
    elif public_only:
        query = query.where(ExamTemplate.is_public == True)
        if not is_developer_role(current_user.role):
            query = query.where(or_(User.role.is_(None), User.role != ROLE_DEVELOPER))
    elif is_admin_scope_role(current_user.role):
        if not is_developer_role(current_user.role):
            query = query.where(or_(User.role.is_(None), User.role != ROLE_DEVELOPER))
    else:
        query = query.where(ExamTemplate.creator_id == current_user.id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Paginate
    offset = (page - 1) * per_page
    query = query.order_by(ExamTemplate.created_at.desc()).offset(offset).limit(per_page)

    result = await db.execute(query)
    templates = result.scalars().all()

    return TemplateListResponse(
        templates=[TemplateResponse.model_validate(t) for t in templates],
        total=total
    )


@router.post("/", response_model=TemplateResponse, status_code=201)
async def create_template(
    template_data: TemplateCreate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    Create new exam template.

    - Teachers can create private templates
    - Only admins can create public templates
    """
    # Only admin can create public templates
    is_public = template_data.is_public if is_admin_scope_role(current_user.role) else False

    template = ExamTemplate(
        name=template_data.name,
        description=template_data.description,
        creator_id=current_user.id,
        template_data=template_data.template_data,
        is_public=is_public
    )

    db.add(template)
    await db.commit()
    await db.refresh(template)

    return template


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Get template details."""
    result = await db.execute(
        select(ExamTemplate, User.role.label("creator_role"))
        .join(User, User.id == ExamTemplate.creator_id, isouter=True)
        .where(ExamTemplate.id == template_id)
    )
    row = result.first()
    template = row[0] if row else None
    creator_role = getattr(row, "creator_role", None) if row else None

    if not template:
        raise HTTPException(404, "Template tidak ditemukan")

    if is_developer_exam_hidden_for_viewer(current_user.role, creator_role):
        raise HTTPException(404, "Template tidak ditemukan")

    # Check access
    if (not template.is_public and
        template.creator_id != current_user.id and
        not is_admin_scope_role(current_user.role)):
        raise HTTPException(403, "Template tidak dapat diakses")

    return template


@router.post("/{template_id}/create-exam", response_model=ExamResponse, status_code=201)
async def create_exam_from_template(
    template_id: int,
    exam_data: ExamFromTemplateCreate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    Create exam from template with customizations.

    Template provides defaults, exam_data can override them.
    """
    # Get template
    result = await db.execute(
        select(ExamTemplate, User.role.label("creator_role"))
        .join(User, User.id == ExamTemplate.creator_id, isouter=True)
        .where(ExamTemplate.id == template_id)
    )
    row = result.first()
    template = row[0] if row else None
    creator_role = getattr(row, "creator_role", None) if row else None

    if not template:
        raise HTTPException(404, "Template tidak ditemukan")

    if is_developer_exam_hidden_for_viewer(current_user.role, creator_role):
        raise HTTPException(404, "Template tidak ditemukan")

    # Check access
    if (not template.is_public and
        template.creator_id != current_user.id and
        not is_admin_scope_role(current_user.role)):
        raise HTTPException(403, "Template tidak dapat diakses")

    # Merge template data with exam customizations
    template_config = template.template_data or {}

    # Use exam_data overrides if provided, else use template defaults
    duration_minutes = exam_data.duration_minutes or template_config.get("duration_minutes", 60)
    passing_score = exam_data.passing_score or template_config.get("passing_score", 70.0)
    max_attempts = exam_data.max_attempts or template_config.get("max_attempts", 1)

    # Generate SEB keys
    seb_config_key = secrets.token_urlsafe(32)
    seb_browser_exam_key = secrets.token_urlsafe(32)

    # Generate unique 6-char access token
    allowed_chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    for _ in range(10):
        access_token = ''.join(secrets.choice(allowed_chars) for _ in range(6))
        existing = await db.execute(
            select(Exam).where(Exam.access_token == access_token)
        )
        if not existing.scalar_one_or_none():
            break
    else:
        raise HTTPException(500, "Gagal membuat access token unik")

    # Create exam
    exam = Exam(
        title=exam_data.title,
        description=exam_data.description,
        creator_id=current_user.id,
        duration_minutes=duration_minutes,
        start_time=exam_data.start_time,
        end_time=exam_data.end_time,
        passing_score=passing_score,
        max_attempts=max_attempts,
        shuffle_questions=template_config.get("shuffle_questions", False),
        shuffle_options=template_config.get("shuffle_options", False),
        show_results=template_config.get("show_results", True),
        allow_review=template_config.get("allow_review", False),
        seb_config_key=seb_config_key,
        seb_browser_exam_key=seb_browser_exam_key,
        access_token=access_token,
        allowed_classes=exam_data.allowed_classes,
        is_published=False  # Created as draft
    )

    db.add(exam)
    await db.commit()
    await db.refresh(exam)

    # ===== COPY QUESTIONS FROM TEMPLATE =====
    from app.models.question import Question, QuestionOption

    questions_data = template_config.get("questions", [])

    for q_data in questions_data:
        # Create question
        question = Question(
            exam_id=exam.id,
            question_text=q_data.get('question_text', ''),
            question_type=q_data.get('question_type', 'multiple_choice'),
            question_subtype=q_data.get('question_subtype'),
            difficulty_level=q_data.get('difficulty_level', 'medium'),
            category_id=q_data.get('category_id'),
            question_settings=q_data.get('question_settings', {}),
            points=q_data.get('points', 1.0),
            order_index=q_data.get('order_index', 0),
            image_url=q_data.get('image_url'),
            pgk_type=q_data.get('pgk_type'),
            stimulus=q_data.get('stimulus'),
            video_url=q_data.get('video_url'),
            audio_url=q_data.get('audio_url')
        )
        db.add(question)
        await db.flush()  # Get question.id

        # Copy options if exist
        options_data = q_data.get('options', [])
        for opt_data in options_data:
            option = QuestionOption(
                question_id=question.id,
                option_text=opt_data.get('option_text', ''),
                is_correct=opt_data.get('is_correct', False),
                order_index=opt_data.get('order_index', 0),
                option_group=opt_data.get('option_group', 'standard'),
                pair_id=opt_data.get('pair_id'),
                option_metadata=opt_data.get('option_metadata', {})
            )
            db.add(option)

    # Commit all questions and options
    await db.commit()
    await db.refresh(exam)

    return ExamResponse.from_orm_with_wib(exam)


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    template_data: TemplateUpdate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Update template (creator or admin only)."""
    result = await db.execute(
        select(ExamTemplate, User.role.label("creator_role"))
        .join(User, User.id == ExamTemplate.creator_id, isouter=True)
        .where(ExamTemplate.id == template_id)
    )
    row = result.first()
    template = row[0] if row else None
    creator_role = getattr(row, "creator_role", None) if row else None

    if not template:
        raise HTTPException(404, "Template tidak ditemukan")

    if is_developer_exam_hidden_for_viewer(current_user.role, creator_role):
        raise HTTPException(404, "Template tidak ditemukan")

    # Authorization
    if template.creator_id != current_user.id and not is_admin_scope_role(current_user.role):
        raise HTTPException(403, "Tidak memiliki akses")

    # Update fields
    if template_data.name is not None:
        template.name = template_data.name
    if template_data.description is not None:
        template.description = template_data.description
    if template_data.template_data is not None:
        template.template_data = template_data.template_data

    # Only admin can change is_public
    if is_admin_scope_role(current_user.role) and template_data.is_public is not None:
        template.is_public = template_data.is_public

    await db.commit()
    await db.refresh(template)

    return template


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Delete template (creator or admin only)."""
    result = await db.execute(
        select(ExamTemplate, User.role.label("creator_role"))
        .join(User, User.id == ExamTemplate.creator_id, isouter=True)
        .where(ExamTemplate.id == template_id)
    )
    row = result.first()
    template = row[0] if row else None
    creator_role = getattr(row, "creator_role", None) if row else None

    if not template:
        raise HTTPException(404, "Template tidak ditemukan")

    if is_developer_exam_hidden_for_viewer(current_user.role, creator_role):
        raise HTTPException(404, "Template tidak ditemukan")

    if template.creator_id != current_user.id and not is_admin_scope_role(current_user.role):
        raise HTTPException(403, "Tidak memiliki akses")

    await db.delete(template)
    await db.commit()

    return {"message": "Template berhasil dihapus"}
