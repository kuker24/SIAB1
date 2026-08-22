"""Schemas for resilient answer sync endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class BatchAnswerItem(BaseModel):
    """Single answer item in batch request."""

    question_id: int
    selected_option_id: Optional[int] = None
    selected_option_ids: Optional[List[int]] = None
    answer_text: Optional[str] = None
    statement_answers: Optional[Dict[str, bool]] = None
    answer_metadata: Optional[Dict[str, Any]] = None


class BatchAutoSaveRequest(BaseModel):
    """Request for batch auto-save with multiple answers."""

    session_id: int
    answers: List[BatchAnswerItem]


class BatchAutoSaveResponse(BaseModel):
    """Response for batch auto-save."""

    status: str
    queued_count: int
    queue_id: str
    timestamp: datetime
