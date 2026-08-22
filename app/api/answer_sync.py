"""Single-answer sync routes.

Public paths remain under /api/exams while the hot-path logic lives in
AnswerSyncService.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, get_current_user_hot_path
from app.database import get_db
from app.schemas.answer import AnswerResponse, AnswerSubmit
from app.services.answer_sync_service import get_answer_sync_service

router = APIRouter(prefix="/api/exams", tags=["Answer Sync"])


@router.post("/submit-answer", response_model=AnswerResponse)
async def submit_answer(
    answer_data: AnswerSubmit,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db),
):
    """Submit a single answer via AnswerSyncService."""
    service = get_answer_sync_service(db, current_user)
    return await service.accept_single_answer(answer_data, request)
