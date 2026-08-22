"""Final submit routes.

Final submit stays a priority path and delegates grading/flush orchestration to
FinalSubmitService.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, get_current_user_hot_path
from app.database import get_db
from app.schemas.answer import ExamSubmitRequest, ExamSubmitResponse
from app.services.final_submit_service import get_final_submit_service

router = APIRouter(prefix="/api/exams", tags=["Final Submit"])


@router.post("/submit", response_model=ExamSubmitResponse)
async def submit_exam(
    submit_data: ExamSubmitRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db),
):
    """Submit entire exam via priority FinalSubmitService."""
    service = get_final_submit_service(db, current_user)
    return await service.submit_exam(submit_data, request)
