from typing import List, Optional, Dict, Any
import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.exam import Exam
from app.models.question import Question
from app.core.cache_manager import cache_manager

logger = logging.getLogger(__name__)

class ExamService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_exam_metadata(self, exam_id: int) -> Optional[Exam]:
        """Get exam metadata (without questions)"""
        # Try cache for metadata? (Phase 3 optimization)
        # For now, DB query
        result = await self.db.execute(select(Exam).where(Exam.id == exam_id))
        return result.scalar_one_or_none()

    async def get_exam_with_settings(self, exam_id: int) -> Optional[Exam]:
        """Get exam metadata + creator info (for start session)"""
        result = await self.db.execute(
            select(Exam)
            .options(selectinload(Exam.creator)) # Need creator for teacher_name
            .where(Exam.id == exam_id)
        )
        return result.scalar_one_or_none()

    async def get_questions_payload(self, exam_id: int) -> List[Dict[str, Any]]:
        """
        Get cached exam questions payload (without is_correct).
        """
        # 1. Try Cache
        cache_key = f"exam:{exam_id}:questions:payload:v1"
        cached_data = await cache_manager.get(cache_key)
        if cached_data:
            return json.loads(cached_data)

        # 2. Database Fallback
        result = await self.db.execute(
            select(Exam)
            .options(
                selectinload(Exam.questions).selectinload(Question.options)
            )
            .where(Exam.id == exam_id)
        )
        exam = result.scalar_one_or_none()

        if not exam:
            return None

        # Build response WITHOUT is_correct
        questions_data = []
        for q in sorted(exam.questions, key=lambda x: x.order_index):
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

        # 3. Set Cache (30 mins)
        await cache_manager.set(cache_key, json.dumps(questions_data, default=str), ttl=1800)

        return questions_data
