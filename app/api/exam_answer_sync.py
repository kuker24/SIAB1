"""Answer sync routes for exam runtime.

Kept separate from ``app.api.exams`` so the large exam CRUD/runtime module can be
reduced gradually without changing public endpoint paths.
"""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import noload

from app.core.security import AuthenticatedUser, get_current_user_hot_path
from app.database import get_db, get_db_read
from app.models.session import Answer, ExamSession
from app.schemas.answer import (
    AnswerJournalSyncRequest,
    AnswerJournalSyncResponse,
    AutoSaveRequest,
    AutoSaveResponse,
)
from app.schemas.answer_sync import BatchAutoSaveRequest, BatchAutoSaveResponse
from app.services.answer_sync_service import get_answer_sync_service

router = APIRouter(prefix="/api/exams", tags=["Exam Answer Sync"])


@router.post("/auto-save", response_model=AutoSaveResponse)
async def auto_save_answers(
    save_data: AutoSaveRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db_read),
):
    """Auto-save multiple answers via internal AnswerSyncService."""
    _ = request
    service = get_answer_sync_service(db, current_user)
    return await service.accept_legacy_autosave(save_data)


@router.get("/session/{session_id}/answers")
async def get_session_answers(
    session_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db_read),
):
    """Get all saved answers for a session for restore on refresh."""
    result = await db.execute(
        select(ExamSession)
        .options(noload("*"))
        .where(
            ExamSession.id == session_id,
            ExamSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status not in ["in_progress", "active"]:
        return {"answers": {}, "session_status": session.status}

    result = await db.execute(
        select(Answer).options(noload("*")).where(Answer.session_id == session_id)
    )
    answers = result.scalars().all()

    answer_dict: Dict[int, object] = {}
    for ans in answers:
        question_id = int(ans.question_id)
        meta = ans.answer_metadata or {}
        if meta.get("statement_answers"):
            answer_dict[question_id] = meta.get("statement_answers")
        elif ans.selected_option_ids is not None and len(ans.selected_option_ids) > 0:
            answer_dict[question_id] = ans.selected_option_ids
        elif ans.answer_text is not None and ans.answer_text.strip():
            answer_dict[question_id] = ans.answer_text
        elif ans.selected_option_id is not None:
            answer_dict[question_id] = ans.selected_option_id

    return {
        "answers": answer_dict,
        "session_status": session.status,
        "answered_count": len(answer_dict),
    }


@router.post("/auto-save-batch", response_model=BatchAutoSaveResponse)
async def auto_save_batch(
    batch_data: BatchAutoSaveRequest,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db),
):
    """Batch auto-save endpoint routed through AnswerSyncService direct mode."""
    _ = request
    service = get_answer_sync_service(db, current_user)
    return await service.accept_batch(batch_data)


@router.post("/answer-journal/sync", response_model=AnswerJournalSyncResponse)
async def sync_answer_journal(
    sync_data: AnswerJournalSyncRequest,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent answer-journal sync endpoint routed through AnswerSyncService."""
    service = get_answer_sync_service(db, current_user)
    return await service.accept_journal_events(sync_data)
