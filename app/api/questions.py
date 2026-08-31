"""
Question management API endpoints.
"""
from typing import List, Set, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload, noload

from app.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.models.question import Question, QuestionOption
from app.models.session import Answer
from app.models.category import QuestionCategory
from app.models.tag import QuestionTag, question_tags_map
from app.schemas.exam import (
    QuestionCreate, QuestionFullResponse, QuestionOptionFullResponse
)
from app.schemas.question_bank import (
    CategoryCreate, CategoryResponse,
    TagCreate, TagResponse, QuestionSearchFilters
)
from app.core.sanitization import sanitize_optional_text, sanitize_safe_media_url
from app.core.security import get_current_teacher, is_pengawas_user
from app.core.roles import (
    ROLE_DEVELOPER,
    is_developer_exam_hidden_for_viewer,
    is_developer_role,
)

router = APIRouter(prefix="/api/questions", tags=["Questions"])


def _enforce_exam_question_visibility(
    current_user: User,
    exam_creator_id: int,
    exam_creator_role: Optional[str],
    *,
    allow_pengawas: bool = False,
) -> None:
    if is_developer_exam_hidden_for_viewer(current_user.role, exam_creator_role):
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")
    if exam_creator_id == current_user.id:
        return
    if bool(getattr(current_user, "is_admin", False)):
        return
    if allow_pengawas and is_pengawas_user(current_user):
        return
    raise HTTPException(status_code=403, detail="Tidak memiliki akses")


def _sanitize_question_payload(question_data: QuestionCreate) -> dict:
    """Normalize question content before persisting it."""
    sanitized_stimulus = sanitize_optional_text(question_data.stimulus, max_length=5000)
    return {
        "question_text": sanitize_optional_text(question_data.question_text, max_length=10000) or "",
        "stimulus": sanitized_stimulus,
        "image_url": sanitize_safe_media_url(question_data.image_url),
        "video_url": sanitize_safe_media_url(question_data.video_url),
        "audio_url": sanitize_safe_media_url(question_data.audio_url),
        "options": [
            sanitize_optional_text(opt.option_text, max_length=5000) or ""
            for opt in question_data.options
        ],
    }


async def _load_question_category(
    db: AsyncSession,
    category_id: Optional[int]
) -> Optional[QuestionCategory]:
    if not category_id:
        return None
    category_result = await db.execute(
        select(QuestionCategory).where(QuestionCategory.id == category_id)
    )
    return category_result.scalar_one_or_none()


async def _load_question_tags(
    db: AsyncSession,
    tag_ids: List[int]
) -> List[QuestionTag]:
    if not tag_ids:
        return []
    tag_result = await db.execute(
        select(QuestionTag).where(QuestionTag.id.in_(tag_ids))
    )
    tags = tag_result.scalars().all()
    tags_by_id = {tag.id: tag for tag in tags}
    return [tags_by_id[tag_id] for tag_id in tag_ids if tag_id in tags_by_id]


def _build_question_response(
    question: Question,
    *,
    options: List[QuestionOption],
    category: Optional[QuestionCategory],
    tags: List[QuestionTag]
) -> QuestionFullResponse:
    return QuestionFullResponse(
        id=question.id,
        question_text=question.question_text,
        stimulus=question.stimulus,
        question_type=question.question_type,
        pgk_type=question.pgk_type,
        difficulty_level=question.difficulty_level,
        category=category,
        tags=tags,
        question_settings=question.question_settings,
        points=question.points,
        order_index=question.order_index,
        image_url=question.image_url,
        video_url=question.video_url,
        audio_url=question.audio_url,
        options=[
            QuestionOptionFullResponse(
                id=opt.id,
                option_text=opt.option_text,
                order_index=opt.order_index,
                option_group=opt.option_group,
                is_correct=opt.is_correct,
                pair_id=opt.pair_id
            )
            for opt in sorted(options, key=lambda x: x.order_index)
        ]
    )


@router.post("/{exam_id}", response_model=QuestionFullResponse, status_code=status.HTTP_201_CREATED)
async def create_question(
    exam_id: int,
    question_data: QuestionCreate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Create a new question for an exam."""
    sanitized_payload = _sanitize_question_payload(question_data)

    # Lightweight permission check.
    exam_owner_result = await db.execute(
        select(Exam.creator_id, User.role.label("creator_role"))
        .join(User, User.id == Exam.creator_id)
        .where(Exam.id == exam_id)
    )
    exam_owner_row = exam_owner_result.first()
    exam_creator_id = int(exam_owner_row.creator_id) if exam_owner_row else None

    if exam_creator_id is None:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    _enforce_exam_question_visibility(
        current_user,
        exam_creator_id,
        getattr(exam_owner_row, "creator_role", None),
    )

    # Create question with settings
    question = Question(
        exam_id=exam_id,
        question_text=sanitized_payload["question_text"],
        stimulus=sanitized_payload["stimulus"],  # NEW: HOTS/AKM stimulus
        question_type=question_data.question_type,
        question_subtype=question_data.question_subtype,
        pgk_type=question_data.pgk_type if question_data.question_type == "multiple_choice_complex" else None,  # NEW: PGK sub-type
        difficulty_level=question_data.difficulty_level,
        category_id=question_data.category_id,
        question_settings={
            **(question_data.question_settings.model_dump() if question_data.question_settings else {}),
            "stimulus": sanitized_payload["stimulus"],
            # "pgk_type": question_data.pgk_type  -- REMOVED: Redundant, stored in column
        },
        points=question_data.points,
        order_index=question_data.order_index,
        image_url=sanitized_payload["image_url"],
        video_url=sanitized_payload["video_url"],  # FIX: Save video URL
        audio_url=sanitized_payload["audio_url"],  # FIX: Save audio URL
    )
    db.add(question)
    await db.flush()

    # Handle tags links
    if question_data.tag_ids:
        await db.execute(
            question_tags_map.insert(),
            [{"question_id": question.id, "tag_id": tag_id} for tag_id in question_data.tag_ids]
        )

    # Create options with grouping support for matching type
    response_options: List[QuestionOption] = []
    for idx, opt_data in enumerate(question_data.options):
        option = QuestionOption(
            question_id=question.id,
            option_text=sanitized_payload["options"][idx],
            is_correct=opt_data.is_correct,
            order_index=opt_data.order_index,
            option_group=opt_data.option_group,
            pair_id=opt_data.pair_id
        )
        db.add(option)
        response_options.append(option)

    await db.commit()

    category = await _load_question_category(db, question.category_id)
    tags = await _load_question_tags(db, question_data.tag_ids)
    return _build_question_response(
        question,
        options=response_options,
        category=category,
        tags=tags,
    )


# ============== QUESTION BANK API (Categories, Tags, Search) ==============


@router.get("/categories", response_model=List[CategoryResponse])
async def get_categories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get all question categories."""
    result = await db.execute(select(QuestionCategory).order_by(QuestionCategory.name))
    return result.scalars().all()


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    category_data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Create a new question category."""
    category = QuestionCategory(
        name=category_data.name,
        description=category_data.description,
        parent_id=category_data.parent_id
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.get("/tags", response_model=List[TagResponse])
async def get_tags(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Get all question tags."""
    result = await db.execute(select(QuestionTag).order_by(QuestionTag.name))
    return result.scalars().all()


@router.post("/tags", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_data: TagCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Create a new question tag."""
    # Check exists
    existing = await db.execute(select(QuestionTag).where(QuestionTag.name == tag_data.name))
    if existing.scalar_one_or_none():
         raise HTTPException(status_code=400, detail="Tag already exists")

    tag = QuestionTag(
        name=tag_data.name,
        color=tag_data.color
    )
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return tag


@router.post("/search", response_model=List[QuestionFullResponse])
async def search_questions(
    filters: QuestionSearchFilters,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_teacher)
):
    """Advanced search for questions."""
    query = select(Question).options(
        selectinload(Question.options),
        selectinload(Question.category),
        selectinload(Question.tags)
    ).join(Exam, Exam.id == Question.exam_id)

    # Teachers can only search questions from their own exams
    if current_user.role == "teacher" and not is_pengawas_user(current_user):
        query = query.where(Exam.creator_id == current_user.id)
    if not is_developer_role(current_user.role):
        query = query.join(User, User.id == Exam.creator_id).where(User.role != ROLE_DEVELOPER)

    if filters.query:
        query = query.where(Question.question_text.ilike(f"%{filters.query}%"))

    if filters.difficulty:
        query = query.where(Question.difficulty_level == filters.difficulty)

    if filters.question_type:
        query = query.where(Question.question_type == filters.question_type)

    if filters.category_id:
        # Include subcategories logic ideally, but clean match for now
        query = query.where(Question.category_id == filters.category_id)

    if filters.tag_ids:
        # Filter by tags (any match)
        query = query.join(Question.tags).where(QuestionTag.id.in_(filters.tag_ids))

    # Pagination
    query = query.offset(filters.offset).limit(filters.limit)

    result = await db.execute(query)
    questions = result.scalars().all()

    # Map to response manually to avoid validation recursion issues if any
    output = []
    for q in questions:
        output.append(QuestionFullResponse(
            id=q.id,
            question_text=q.question_text,
            question_type=q.question_type,
            difficulty_level=q.difficulty_level,
            category=q.category,
            tags=q.tags,
            question_settings=q.question_settings,
            points=q.points,
            order_index=q.order_index,
            image_url=q.image_url,
            options=[
                QuestionOptionFullResponse(
                    id=opt.id,
                    option_text=opt.option_text,
                    order_index=opt.order_index,
                    option_group=opt.option_group,
                    is_correct=opt.is_correct,
                    pair_id=opt.pair_id
                )
                for opt in sorted(q.options, key=lambda x: x.order_index)
            ]
        ))

    return output


# Existing GET all...
@router.get("/{exam_id}/all", response_model=List[QuestionFullResponse])
async def get_all_questions(
    exam_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Get all questions for an exam (with correct answers - teachers only)."""
    # Lightweight permission check without loading full exam relationships.
    exam_owner_result = await db.execute(
        select(Exam.creator_id, User.role.label("creator_role"))
        .join(User, User.id == Exam.creator_id)
        .where(Exam.id == exam_id)
    )
    exam_owner_row = exam_owner_result.first()
    exam_creator_id = int(exam_owner_row.creator_id) if exam_owner_row else None
    if exam_creator_id is None:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    _enforce_exam_question_visibility(
        current_user,
        exam_creator_id,
        getattr(exam_owner_row, "creator_role", None),
        allow_pengawas=False,
    )

    result = await db.execute(
        select(Question)
        .options(
            selectinload(Question.options),
            noload(Question.exam),
            noload(Question.category),
            noload(Question.tags),
            noload(Question.answers),
        )
        .where(Question.exam_id == exam_id)
        .order_by(Question.order_index)
    )
    questions = result.scalars().all()

    return [
        QuestionFullResponse(
            id=q.id,
            question_text=q.question_text,
            stimulus=q.stimulus,  # FIX: Return stimulus
            question_type=q.question_type,
            pgk_type=q.pgk_type,  # FIX: Return pgk_type
            difficulty_level=q.difficulty_level,
            category=None,
            tags=[],
            question_settings=q.question_settings,
            points=q.points,
            order_index=q.order_index,
            image_url=q.image_url,
            video_url=q.video_url,  # FIX: Return video URL
            audio_url=q.audio_url,  # FIX: Return audio URL
            options=[
                QuestionOptionFullResponse(
                    id=opt.id,
                    option_text=opt.option_text,
                    order_index=opt.order_index,
                    option_group=opt.option_group,
                    is_correct=opt.is_correct,
                    pair_id=opt.pair_id
                )
                for opt in sorted(q.options, key=lambda x: x.order_index)
            ]
        )
        for q in questions
    ]


@router.put("/{question_id}", response_model=QuestionFullResponse)
async def update_question(
    question_id: int,
    question_data: QuestionCreate,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Update a question."""
    sanitized_payload = _sanitize_question_payload(question_data)

    result = await db.execute(
        select(Question)
        .options(
            selectinload(Question.options),
            noload(Question.exam),
            noload(Question.answers),
            noload(Question.category),
            noload(Question.tags),
        )
        .where(Question.id == question_id)
    )
    question = result.scalar_one_or_none()

    if not question:
        raise HTTPException(status_code=404, detail="Soal tidak ditemukan")

    # Check permission without loading full exam relationship tree.
    exam_owner_result = await db.execute(
        select(Exam.creator_id, User.role.label("creator_role"))
        .join(User, User.id == Exam.creator_id)
        .where(Exam.id == question.exam_id)
    )
    exam_owner_row = exam_owner_result.first()
    exam_creator_id = int(exam_owner_row.creator_id) if exam_owner_row else None
    if exam_creator_id is None:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    _enforce_exam_question_visibility(
        current_user,
        exam_creator_id,
        getattr(exam_owner_row, "creator_role", None),
    )

    # Prepare option changes early for conditional answer-history checks.
    existing_options = sorted(question.options, key=lambda x: x.order_index)
    incoming_options = sorted(question_data.options, key=lambda x: x.order_index)

    type_change_requested = question_data.question_type != question.question_type
    options_shrinking = len(incoming_options) < len(existing_options)
    needs_answer_history = type_change_requested or options_shrinking

    referenced_option_ids: Set[int] = set()
    has_answer_history = False
    if needs_answer_history:
        removable_options = existing_options[min(len(existing_options), len(incoming_options)):]
        removable_option_ids = [opt.id for opt in removable_options]

        if removable_option_ids:
            # Only inspect answers that reference options about to be removed.
            answer_rows = await db.execute(
                select(Answer.selected_option_id, Answer.selected_option_ids)
                .where(
                    Answer.question_id == question.id,
                    or_(
                        Answer.selected_option_id.in_(removable_option_ids),
                        Answer.selected_option_ids.op("&&")(removable_option_ids)
                    )
                )
            )
            for selected_option_id, selected_option_ids in answer_rows.all():
                has_answer_history = True
                if selected_option_id is not None:
                    referenced_option_ids.add(int(selected_option_id))
                if selected_option_ids:
                    for option_id in selected_option_ids:
                        if option_id is not None:
                            referenced_option_ids.add(int(option_id))
        else:
            # Type-change guard: only need existence check, no full scan.
            any_answer_result = await db.execute(
                select(Answer.id).where(Answer.question_id == question.id).limit(1)
            )
            has_answer_history = any_answer_result.scalar_one_or_none() is not None

    if has_answer_history and question_data.question_type != question.question_type:
        raise HTTPException(
            status_code=400,
            detail=(
                "Tipe soal tidak dapat diubah karena sudah ada jawaban siswa. "
                "Duplikasi soal/ujian jika ingin mengganti tipe."
            )
        )

    # Update question with settings
    question.question_text = sanitized_payload["question_text"]
    question.stimulus = sanitized_payload["stimulus"]  # NEW: Update stimulus
    question.question_type = question_data.question_type
    question.question_subtype = question_data.question_subtype
    question.pgk_type = question_data.pgk_type if question_data.question_type == "multiple_choice_complex" else None  # NEW: Update PGK sub-type
    question.difficulty_level = question_data.difficulty_level
    question.category_id = question_data.category_id
    question.question_settings = {
        **(question_data.question_settings.model_dump() if question_data.question_settings else {}),
        "stimulus": sanitized_payload["stimulus"],
        # "pgk_type": question_data.pgk_type -- REMOVED: Redundant
    }
    question.points = question_data.points
    question.order_index = question_data.order_index
    question.image_url = sanitized_payload["image_url"]
    question.video_url = sanitized_payload["video_url"]  # FIX: Update video URL
    question.audio_url = sanitized_payload["audio_url"]  # FIX: Update audio URL

    # Update Tags
    # Clear existing
    await db.execute(
        question_tags_map.delete().where(question_tags_map.c.question_id == question.id)
    )
    # Add new
    if question_data.tag_ids:
        await db.execute(
            question_tags_map.insert(),
            [{"question_id": question.id, "tag_id": tag_id} for tag_id in question_data.tag_ids]
        )

    # Update options in-place to preserve option IDs referenced by answers.
    common_len = min(len(existing_options), len(incoming_options))

    for idx in range(common_len):
        opt = existing_options[idx]
        opt_data = incoming_options[idx]
        opt.option_text = sanitize_optional_text(opt_data.option_text, max_length=5000) or ""
        opt.is_correct = opt_data.is_correct
        opt.order_index = opt_data.order_index
        opt.option_group = opt_data.option_group
        opt.pair_id = opt_data.pair_id

    # Add new options if payload has more than current DB rows.
    added_options: List[QuestionOption] = []
    for opt_data in incoming_options[common_len:]:
        new_option = QuestionOption(
            question_id=question.id,
            option_text=sanitize_optional_text(opt_data.option_text, max_length=5000) or "",
            is_correct=opt_data.is_correct,
            order_index=opt_data.order_index,
            option_group=opt_data.option_group,
            pair_id=opt_data.pair_id
        )
        db.add(new_option)
        added_options.append(new_option)

    # Delete surplus options only when they are not referenced by existing answers.
    removable_options = existing_options[common_len:]
    protected_options = [opt for opt in removable_options if opt.id in referenced_option_ids]
    if protected_options:
        raise HTTPException(
            status_code=400,
            detail=(
                "Sebagian opsi lama sudah dipakai jawaban siswa, jadi tidak bisa dihapus. "
                "Kurangi perubahan struktur opsi atau duplikasi ujian untuk sesi berikutnya."
            )
        )
    for opt in removable_options:
        await db.delete(opt)

    await db.commit()

    response_options = existing_options[:common_len] + added_options
    category = await _load_question_category(db, question.category_id)
    tags = await _load_question_tags(db, question_data.tag_ids)
    return _build_question_response(
        question,
        options=response_options,
        category=category,
        tags=tags,
    )


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(
    question_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Delete a question."""
    result = await db.execute(
        select(Question)
        .options(noload(Question.exam))
        .where(Question.id == question_id)
    )
    question = result.scalar_one_or_none()

    if not question:
        raise HTTPException(status_code=404, detail="Soal tidak ditemukan")

    # Check permission without loading full exam relationship tree.
    exam_owner_result = await db.execute(
        select(Exam.creator_id, User.role.label("creator_role"))
        .join(User, User.id == Exam.creator_id)
        .where(Exam.id == question.exam_id)
    )
    exam_owner_row = exam_owner_result.first()
    exam_creator_id = int(exam_owner_row.creator_id) if exam_owner_row else None
    if exam_creator_id is None:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")

    _enforce_exam_question_visibility(
        current_user,
        exam_creator_id,
        getattr(exam_owner_row, "creator_role", None),
    )

    await db.delete(question)
    await db.commit()
