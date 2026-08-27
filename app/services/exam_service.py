from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, true
from sqlalchemy.orm import joinedload, noload, selectinload
from sqlalchemy.sql import Select

from app.models.exam import Exam
from app.models.question import Question
from app.models.session import ExamSession
from app.models.user import User
from app.core.cache_manager import cache_manager
from app.core.singleflight import KeyedSingleFlight
from app.core.start_db_admission import start_db_segment
from app.database import async_session_read

logger = logging.getLogger(__name__)
_question_payload_fills = KeyedSingleFlight[str]()


@dataclass(frozen=True)
class ExamStartCreatorView:
    full_name: Optional[str]
    role: Optional[str]


@dataclass(frozen=True)
class ExamStartProjection:
    id: int
    creator_id: int
    is_published: bool
    start_time: datetime
    end_time: datetime
    max_attempts: int
    allowed_classes: Optional[str]
    allowed_students: Optional[str]
    duration_minutes: int
    shuffle_questions: bool
    shuffle_options: bool
    title: str
    subject: Optional[str]
    exam_type: Optional[str]
    show_results: bool
    show_teacher_name: Optional[bool]
    creator: Optional[ExamStartCreatorView]


COMPLETED_ATTEMPT_STATUSES = ("completed", "submitted")
START_EXISTING_SESSION_STATUSES = ("in_progress", "active", "terminated", "kicked")
START_EXISTING_SESSION_LIMIT = 16


@dataclass
class ExamStartSessionRow:
    id: int
    status: str
    start_time: datetime
    end_time: Optional[datetime]
    terminated_by_admin: bool
    emergency_exit_allowed: bool
    violation_count: int
    total_paused_seconds: int


@dataclass
class ExamStartSessionState:
    attempt_count: int
    existing_sessions: List[ExamStartSessionRow]


def build_exam_start_session_state_statement(
    user_id: int,
    exam_id: int,
) -> Select:
    attempt_count_subq = (
        select(func.count(ExamSession.id).label("attempt_count"))
        .where(
            ExamSession.user_id == user_id,
            ExamSession.exam_id == exam_id,
            ExamSession.status.in_(COMPLETED_ATTEMPT_STATUSES),
        )
        .subquery()
    )
    existing_subq = (
        select(
            ExamSession.id,
            ExamSession.status,
            ExamSession.start_time,
            ExamSession.end_time,
            ExamSession.terminated_by_admin,
            ExamSession.emergency_exit_allowed,
            ExamSession.violation_count,
            ExamSession.total_paused_seconds,
        )
        .where(
            ExamSession.user_id == user_id,
            ExamSession.exam_id == exam_id,
            ExamSession.status.in_(START_EXISTING_SESSION_STATUSES),
        )
        .order_by(ExamSession.start_time.desc(), ExamSession.id.desc())
        .limit(START_EXISTING_SESSION_LIMIT)
        .subquery()
    )
    return (
        select(
            attempt_count_subq.c.attempt_count,
            existing_subq.c.id,
            existing_subq.c.status,
            existing_subq.c.start_time,
            existing_subq.c.end_time,
            existing_subq.c.terminated_by_admin,
            existing_subq.c.emergency_exit_allowed,
            existing_subq.c.violation_count,
            existing_subq.c.total_paused_seconds,
        )
        .select_from(attempt_count_subq)
        .outerjoin(existing_subq, true())
    )


class ExamService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_exam_metadata(self, exam_id: int) -> Optional[Exam]:
        """Get exam metadata (without questions)"""
        result = await self.db.execute(
            select(Exam).options(noload("*")).where(Exam.id == exam_id)
        )
        return result.scalar_one_or_none()

    async def get_exam_with_settings(self, exam_id: int) -> Optional[Exam]:
        """Get exam metadata + creator info (for start session)"""
        result = await self.db.execute(
            select(Exam)
            .options(
                noload("*"),
                joinedload(Exam.creator).options(noload("*")),
            )
            .where(Exam.id == exam_id)
        )
        return result.scalar_one_or_none()

    async def get_exam_start_projection(
        self,
        exam_id: int,
    ) -> Optional[ExamStartProjection]:
        result = await self.db.execute(
            select(
                Exam.id,
                Exam.creator_id,
                Exam.is_published,
                Exam.start_time,
                Exam.end_time,
                Exam.max_attempts,
                Exam.allowed_classes,
                Exam.allowed_students,
                Exam.duration_minutes,
                Exam.shuffle_questions,
                Exam.shuffle_options,
                Exam.title,
                Exam.subject,
                Exam.exam_type,
                Exam.show_results,
                Exam.show_teacher_name,
                User.full_name,
                User.role,
            )
            .select_from(Exam)
            .outerjoin(User, User.id == Exam.creator_id)
            .where(Exam.id == exam_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        creator = None
        if row.full_name is not None or row.role is not None:
            creator = ExamStartCreatorView(
                full_name=row.full_name,
                role=row.role,
            )
        return ExamStartProjection(
            id=int(row.id),
            creator_id=int(row.creator_id),
            is_published=bool(row.is_published),
            start_time=row.start_time,
            end_time=row.end_time,
            max_attempts=int(row.max_attempts or 1),
            allowed_classes=row.allowed_classes,
            allowed_students=row.allowed_students,
            duration_minutes=int(row.duration_minutes or 0),
            shuffle_questions=bool(row.shuffle_questions),
            shuffle_options=bool(row.shuffle_options),
            title=str(row.title),
            subject=row.subject,
            exam_type=row.exam_type,
            show_results=bool(row.show_results),
            show_teacher_name=row.show_teacher_name,
            creator=creator,
        )

    async def get_exam_start_session_state(
        self,
        user_id: int,
        exam_id: int,
    ) -> ExamStartSessionState:
        result = await self.db.execute(
            build_exam_start_session_state_statement(user_id, exam_id)
        )
        rows = result.all()
        attempt_count = 0
        existing_sessions: List[ExamStartSessionRow] = []
        for row in rows:
            attempt_count = int(row.attempt_count or 0)
            if row.id is None:
                continue
            existing_sessions.append(
                ExamStartSessionRow(
                    id=int(row.id),
                    status=str(row.status),
                    start_time=row.start_time,
                    end_time=row.end_time,
                    terminated_by_admin=bool(row.terminated_by_admin),
                    emergency_exit_allowed=bool(row.emergency_exit_allowed),
                    violation_count=int(row.violation_count or 0),
                    total_paused_seconds=int(row.total_paused_seconds or 0),
                )
            )
        return ExamStartSessionState(
            attempt_count=attempt_count,
            existing_sessions=existing_sessions,
        )

    async def get_questions_payload(self, exam_id: int) -> List[Dict[str, Any]]:
        """
        Get cached exam questions payload (without is_correct).
        """
        # 1. Try Cache
        cache_key = f"exam:{exam_id}:questions:payload:v1"
        cached_data = await cache_manager.get(cache_key)
        if cached_data:
            return json.loads(cached_data)

        async def fill() -> str:
            refreshed = await cache_manager.get(cache_key)
            if refreshed:
                return refreshed
            async with start_db_segment("questions"):
                async with async_session_read() as db:
                    result = await db.execute(
                        select(Question)
                        .options(
                            noload("*"),
                            selectinload(Question.options).options(noload("*")),
                        )
                        .where(Question.exam_id == exam_id)
                    )
                    questions = list(result.scalars().all())
                    questions_data = []
                    for q in sorted(questions, key=lambda x: x.order_index):
                        options = [
                            {
                                "id": opt.id,
                                "option_text": opt.option_text,
                                "order_index": opt.order_index,
                                "option_group": opt.option_group or "standard",
                                "pair_id": opt.pair_id
                            }
                            for opt in sorted(q.options, key=lambda x: x.order_index)
                        ]
                        questions_data.append({
                            "id": q.id,
                            "question_text": q.question_text,
                            "stimulus": q.stimulus,
                            "question_type": q.question_type,
                            "pgk_type": q.pgk_type,
                            "points": q.points,
                            "order_index": q.order_index,
                            "image_url": q.image_url,
                            "video_url": q.video_url,
                            "audio_url": q.audio_url,
                            "question_settings": q.question_settings or {},
                            "options": options
                        })

            serialized = json.dumps(questions_data, default=str)
            await cache_manager.set(cache_key, serialized, ttl=1800)
            return serialized

        return json.loads(await _question_payload_fills.run(cache_key, fill))
