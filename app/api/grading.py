"""
Grading API endpoints for manual essay evaluation.
Supports single and batch grading with feedback.
"""
from typing import List, Optional, Dict
from sqlalchemy import or_, and_
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, ConfigDict

from app.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.models.question import Question
from app.models.session import ExamSession, Answer
from app.core.security import get_current_teacher
from app.core.roles import (
    ROLE_ADMIN,
    ROLE_DEVELOPER,
    ROLE_TEACHER,
    is_developer_exam_hidden_for_viewer,
    normalize_role,
)

router = APIRouter(prefix="/api/grading", tags=["Grading"])

GRADABLE_SESSION_STATUSES = ("submitted", "completed")


def _grading_role(current_user: User) -> str:
    return normalize_role(getattr(current_user, "role", None))


def _requires_own_exam_grading_scope(current_user: User) -> bool:
    return _grading_role(current_user) in {ROLE_TEACHER, ROLE_DEVELOPER}


def _can_grade_exam_creator(current_user: User, exam_creator_id: int) -> bool:
    role = _grading_role(current_user)
    if role in {ROLE_TEACHER, ROLE_DEVELOPER}:
        return int(exam_creator_id) == int(current_user.id)
    return role == ROLE_ADMIN


def _apply_grading_query_scope(query, current_user: User):
    """Apply grading visibility rules.

    Teachers and developers may grade only exams they created. Admins keep the
    existing control-plane visibility and do not see developer-authored exams.
    """
    role = _grading_role(current_user)
    if role in {ROLE_TEACHER, ROLE_DEVELOPER}:
        return query.where(Exam.creator_id == current_user.id)
    if role == ROLE_ADMIN:
        return query.where(Exam.creator.has(User.role != ROLE_DEVELOPER))
    raise HTTPException(status_code=403, detail="Not authorized")


async def _assert_grading_exam_access(
    db: AsyncSession,
    current_user: User,
    exam_creator_id: int,
) -> None:
    creator_role_result = await db.execute(
        select(User.role).where(User.id == exam_creator_id)
    )
    creator_role = creator_role_result.scalar_one_or_none()
    if is_developer_exam_hidden_for_viewer(current_user.role, creator_role):
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")
    if not _can_grade_exam_creator(current_user, exam_creator_id):
        raise HTTPException(403, "Not authorized")


# === Schemas ===

class PendingEssay(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    answer_id: int
    student_name: str
    student_username: str
    student_class: Optional[str]
    exam_id: int
    exam_title: str
    question_id: int
    question_text: str
    question_type: str  # 'essay' or 'short_answer'
    answer_text: Optional[str]
    max_points: float
    submitted_at: Optional[datetime]
    correct_answer: Optional[str] = None  # For short_answer hint
    question_settings: Optional[dict] = None  # Include question settings for grading mode

class GradeEssayRequest(BaseModel):
    answer_id: int
    points_earned: float
    feedback: Optional[str] = None


class BatchGradeItem(BaseModel):
    answer_id: int
    points: float
    feedback: Optional[str] = None


class BatchGradeRequest(BaseModel):
    grades: List[BatchGradeItem]


class GradingStats(BaseModel):
    total_pending: int
    by_exam: Dict[str, int]
    recently_graded: int


# === Endpoints ===

@router.get("/pending-essays")
async def get_pending_essays(
    exam_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all essay answers pending manual grading.

    Teachers can only see essays from their own exams.
    Admins can see all essays.
    """

    # Build base query for essay answers that haven't been graded
    # FIX: Include answers dengan answer_text tidak null (meskipun is_correct sudah di-set)
    query = (
        select(Answer)
        .join(Question, Answer.question_id == Question.id)
        .join(ExamSession, Answer.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .join(User, ExamSession.user_id == User.id)
        .options(
            selectinload(Answer.question),
            selectinload(Answer.session).selectinload(ExamSession.user),
            selectinload(Answer.session).selectinload(ExamSession.exam)
        )
        .where(
            and_(
                Exam.is_deleted == False,  # FIX: Exclude deleted exams
                ExamSession.status.in_(GRADABLE_SESSION_STATUSES),
                Question.question_type.in_(['essay', 'short_answer']),
                Answer.answer_text.isnot(None),  # Pastikan ada jawaban teks
                or_(
                    # Belum dinilai sama sekali (NULL)
                    Answer.is_correct.is_(None),
                    # Short answers yang auto-graded FALSE (allow manual override)
                    and_(
                        Question.question_type == 'short_answer',
                        Answer.is_correct == False
                    )
                )
            )
        )
    )

    query = _apply_grading_query_scope(query, current_user)

    # Filter by specific exam if provided
    if exam_id:
        query = query.where(ExamSession.exam_id == exam_id)

    # Order by submission time (oldest first for fair grading)
    query = query.order_by(Answer.answered_at.asc())

    # Count total for pagination
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    answers = result.scalars().all()

    # Build response
    pending = []
    for ans in answers:
        # Get correct answer for short answer questions
        correct_answer_hint = None
        if ans.question.question_type == 'short_answer':
            acceptable_answers = ans.question.question_settings.get('acceptable_answers', []) if ans.question.question_settings else []
            if acceptable_answers:
                correct_answer_hint = acceptable_answers[0] if len(acceptable_answers) == 1 else ', '.join(acceptable_answers[:3])

        pending.append(PendingEssay(
            answer_id=ans.id,
            student_name=ans.session.user.full_name,
            student_username=ans.session.user.username,
            student_class=ans.session.user.student_class,
            exam_id=ans.session.exam.id,
            exam_title=ans.session.exam.title,
            question_id=ans.question.id,
            question_text=ans.question.question_text,
            question_type=ans.question.question_type,  # Include type
            answer_text=ans.answer_text,
            max_points=float(ans.question.points),
            submitted_at=ans.answered_at,
            correct_answer=correct_answer_hint,
            question_settings=ans.question.question_settings  # Include question settings for frontend
        ))

    return {
        "pending": [p.model_dump() for p in pending],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 0
    }


@router.get("/stats")
async def get_grading_stats(
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Get grading statistics for the current user."""

    # Base query for pending essays
    pending_query = (
        select(func.count(Answer.id))
        .join(Question, Answer.question_id == Question.id)
        .join(ExamSession, Answer.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(
            Exam.is_deleted == False,  # FIX: Exclude deleted exams
            ExamSession.status.in_(GRADABLE_SESSION_STATUSES),
            or_(
                and_(
                    Question.question_type.in_(['essay', 'short_answer']),
                    Answer.is_correct.is_(None)
                ),
                and_(
                    Question.question_type == 'short_answer',
                    Answer.is_correct == False
                )
            )
        )
    )

    pending_query = _apply_grading_query_scope(pending_query, current_user)

    total_pending = (await db.execute(pending_query)).scalar() or 0

    # Count essay separately
    essay_query = (
        select(func.count(Answer.id))
        .join(Question, Answer.question_id == Question.id)
        .join(ExamSession, Answer.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(
            Exam.is_deleted == False,  # FIX: Exclude deleted exams
            ExamSession.status.in_(GRADABLE_SESSION_STATUSES),
            Question.question_type == 'essay',
            Answer.is_correct.is_(None)
        )
    )

    essay_query = _apply_grading_query_scope(essay_query, current_user)

    essay_pending = (await db.execute(essay_query)).scalar() or 0

    # Count short answer separately
    short_answer_query = (
        select(func.count(Answer.id))
        .join(Question, Answer.question_id == Question.id)
        .join(ExamSession, Answer.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(
            Exam.is_deleted == False,  # FIX: Exclude deleted exams
            ExamSession.status.in_(GRADABLE_SESSION_STATUSES),
            Question.question_type == 'short_answer',
            or_(
                Answer.is_correct.is_(None),
                Answer.is_correct == False  # Include auto-graded wrong answers
            )
        )
    )

    short_answer_query = _apply_grading_query_scope(short_answer_query, current_user)

    short_answer_pending = (await db.execute(short_answer_query)).scalar() or 0

    # Group by exam (support both types)
    by_exam_query = (
        select(Exam.title, func.count(Answer.id))
        .join(Question, Answer.question_id == Question.id)
        .join(ExamSession, Answer.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(
            Exam.is_deleted == False,  # FIX: Exclude deleted exams
            ExamSession.status.in_(GRADABLE_SESSION_STATUSES),
            or_(
                and_(
                    Question.question_type.in_(['essay', 'short_answer']),
                    Answer.is_correct.is_(None)
                ),
                and_(
                    Question.question_type == 'short_answer',
                    Answer.is_correct == False
                )
            )
        )
        .group_by(Exam.id, Exam.title)
    )

    by_exam_query = _apply_grading_query_scope(by_exam_query, current_user)

    by_exam_result = await db.execute(by_exam_query)
    by_exam = {title: count for title, count in by_exam_result}

    # Recently graded (last 24 hours)
    yesterday = datetime.now(timezone.utc) - timedelta(hours=24)

    recent_query = (
        select(func.count(Answer.id))
        .join(Question, Answer.question_id == Question.id)
        .join(ExamSession, Answer.session_id == ExamSession.id)
        .join(Exam, ExamSession.exam_id == Exam.id)
        .where(
            ExamSession.status.in_(GRADABLE_SESSION_STATUSES),
            Question.question_type.in_(['essay', 'short_answer']),  # Support both types
            Answer.is_correct.is_not(None),
            Answer.answered_at >= yesterday
        )
    )

    recent_query = _apply_grading_query_scope(recent_query, current_user)

    recently_graded = (await db.execute(recent_query)).scalar() or 0

    return {
        "total_pending": total_pending,
        "essay_pending": essay_pending,
        "short_answer_pending": short_answer_pending,
        "by_exam": by_exam,
        "recently_graded": recently_graded
    }


@router.post("/grade-essay")
async def grade_essay(
    request: GradeEssayRequest,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    Grade a single essay answer.

    Validates:
    - Answer exists
    - Teacher owns the exam (or is admin)
    - Points are within valid range
    """

    # Get answer with relationships
    result = await db.execute(
        select(Answer)
        .options(
            selectinload(Answer.question),
            selectinload(Answer.session).selectinload(ExamSession.exam)
        )
        .where(Answer.id == request.answer_id)
    )
    answer = result.scalar_one_or_none()

    if not answer:
        raise HTTPException(404, "Answer not found")

    await _assert_grading_exam_access(
        db,
        current_user,
        int(answer.session.exam.creator_id),
    )

    if answer.session.status not in GRADABLE_SESSION_STATUSES:
        raise HTTPException(
            400,
            "Jawaban tidak bisa dinilai karena sesi belum submitted/completed"
        )

    # Validate points - allow up to question's max points or higher for flexibility
    max_points = float(answer.question.points)
    # Allow grading up to 2x the question points for partial credit flexibility
    allowed_max = max_points * 2
    if request.points_earned < 0 or request.points_earned > allowed_max:
        raise HTTPException(400, f"Points must be between 0 and {allowed_max}")

    # Update answer
    answer.points_earned = request.points_earned
    # FIX: Mark as graded (True) regardless of points value to remove from pending
    # is_correct = True means "has been graded", not necessarily "correct answer"
    answer.is_correct = True

    # Store grading metadata
    metadata = answer.answer_metadata or {}
    metadata["grader_feedback"] = request.feedback or ""
    metadata["graded_by"] = current_user.id
    metadata["grader_name"] = current_user.full_name
    metadata["graded_at"] = datetime.now(timezone.utc).isoformat()
    answer.answer_metadata = metadata

    await db.commit()

    # Recalculate session score
    await recalculate_session_score(answer.session_id, db)

    return {
        "success": True,
        "graded": True,
        "answer_id": request.answer_id,
        "points_earned": request.points_earned
    }


@router.post("/batch-grade")
async def batch_grade_essays(
    request: BatchGradeRequest,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """
    Batch grade multiple essays at once.

    Useful for quickly grading multiple answers with similar scores.
    """

    graded_count = 0
    errors = []
    session_ids_to_recalculate = set()

    for grade in request.grades:
        try:
            # Get answer
            result = await db.execute(
                select(Answer)
                .options(
                    selectinload(Answer.question),
                    selectinload(Answer.session).selectinload(ExamSession.exam)
                )
                .where(Answer.id == grade.answer_id)
            )
            answer = result.scalar_one_or_none()

            if not answer:
                errors.append({"answer_id": grade.answer_id, "error": "Answer not found"})
                continue

            try:
                await _assert_grading_exam_access(
                    db,
                    current_user,
                    int(answer.session.exam.creator_id),
                )
            except HTTPException as exc:
                errors.append({"answer_id": grade.answer_id, "error": str(exc.detail)})
                continue

            if answer.session.status not in GRADABLE_SESSION_STATUSES:
                errors.append({
                    "answer_id": grade.answer_id,
                    "error": "Session not submitted/completed"
                })
                continue

            # Validate points - allow up to 2x for flexibility
            max_points = float(answer.question.points)
            allowed_max = max_points * 2
            if grade.points < 0 or grade.points > allowed_max:
                errors.append({"answer_id": grade.answer_id, "error": f"Points must be 0-{allowed_max}"})
                continue

            # Update answer
            answer.points_earned = grade.points
            # FIX: Mark as graded (True) to remove from pending list
            answer.is_correct = True

            metadata = answer.answer_metadata or {}
            metadata["grader_feedback"] = grade.feedback or ""
            metadata["graded_by"] = current_user.id
            metadata["graded_at"] = datetime.now(timezone.utc).isoformat()
            answer.answer_metadata = metadata

            session_ids_to_recalculate.add(answer.session_id)
            graded_count += 1

        except Exception as e:
            errors.append({"answer_id": grade.answer_id, "error": str(e)})

    await db.commit()

    # Recalculate all affected session scores
    for session_id in session_ids_to_recalculate:
        await recalculate_session_score(session_id, db)

    return {
        "success": True,
        "graded": graded_count,
        "errors": errors,
        "sessions_updated": len(session_ids_to_recalculate)
    }


@router.get("/answer/{answer_id}")
async def get_answer_detail(
    answer_id: int,
    current_user: User = Depends(get_current_teacher),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed information about a specific answer for grading."""

    result = await db.execute(
        select(Answer)
        .options(
            selectinload(Answer.question).selectinload(Question.options),
            selectinload(Answer.session).selectinload(ExamSession.user),
            selectinload(Answer.session).selectinload(ExamSession.exam)
        )
        .where(Answer.id == answer_id)
    )
    answer = result.scalar_one_or_none()

    if not answer:
        raise HTTPException(404, "Answer not found")

    await _assert_grading_exam_access(
        db,
        current_user,
        int(answer.session.exam.creator_id),
    )

    return {
        "answer_id": answer.id,
        "student": {
            "id": answer.session.user.id,
            "name": answer.session.user.full_name,
            "username": answer.session.user.username,
            "class": answer.session.user.student_class
        },
        "exam": {
            "id": answer.session.exam.id,
            "title": answer.session.exam.title
        },
        "question": {
            "id": answer.question.id,
            "text": answer.question.question_text,
            "type": answer.question.question_type,
            "max_points": float(answer.question.points),
            "image_url": answer.question.image_url
        },
        "answer_text": answer.answer_text,
        "current_grade": {
            "points_earned": (
                float(answer.points_earned)
                if answer.points_earned is not None
                else None
            ),
            "is_correct": answer.is_correct,
            "feedback": (answer.answer_metadata or {}).get("grader_feedback"),
            "graded_at": (answer.answer_metadata or {}).get("graded_at")
        },
        "submitted_at": answer.answered_at.isoformat() if answer.answered_at else None
    }


async def recalculate_session_score(session_id: int, db: AsyncSession):
    """
    Recalculate total session score after grading an essay.

    This ensures the overall exam score reflects the manual grading.
    Fixed to calculate total_possible from Exam Questions, not just answered ones.
    """

    # Get session with exam and questions
    session_result = await db.execute(
        select(ExamSession)
        .options(selectinload(ExamSession.exam).selectinload(Exam.questions))
        .where(ExamSession.id == session_id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        return

    # Get all answers for session
    result = await db.execute(
        select(Answer)
        .where(Answer.session_id == session_id)
    )
    answers = result.scalars().all()

    # Calculate total points earned and possible
    total_earned = 0
    total_possible = sum(float(q.points) for q in session.exam.questions)

    for a in answers:
        if a.points_earned is not None:
            total_earned += float(a.points_earned)

    # Calculate percentage score
    if total_possible > 0:
        score = (total_earned / total_possible) * 100
    else:
        score = 0

    # Update session score
    session.score = round(score, 2)
    await db.commit()
