"""
Answer Pydantic schemas for request/response validation.
ENHANCED v2.0 - Added validators for type coercion and better error messages
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, field_validator, Field


class AnswerSubmit(BaseModel):
    """
    Schema for submitting a single answer - supports all question types.
    
    ENHANCED with validators for automatic type coercion from frontend.
    """
    session_id: int = Field(..., description="Session ID (integer)")
    question_id: int = Field(..., description="Question ID (integer)")
    
    # Single selection (multiple_choice, true_false)
    selected_option_id: Optional[int] = Field(None, description="Selected option ID for single choice")
    
    # Multiple selections (multiple_choice_complex)
    selected_option_ids: Optional[List[int]] = Field(None, description="List of selected option IDs for multiple choice")
    
    # Matching pairs answer (DEPRECATED - kept for backward compatibility)
    matching_pairs: Optional[Dict[str, int]] = Field(None, description="Dictionary of matching pairs (deprecated)")
    
    # True/False table answers: {statement_id: true/false}
    statement_answers: Optional[Dict[str, bool]] = Field(None, description="Dict of statement boolean answers")
    
    # Text answer (essay, short_answer)
    answer_text: Optional[str] = Field(None, description="Text answer for essay/short answer")
    
    # Flexible metadata
    answer_metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator('session_id', 'question_id', mode='before')
    @classmethod
    def coerce_to_int(cls, v):
        """Coerce session_id and question_id to integers."""
        if v is None:
            raise ValueError("Field cannot be None")
        try:
            return int(v)
        except (ValueError, TypeError):
            raise ValueError(f"Must be a valid integer, got: {v}")

    @field_validator('selected_option_id', mode='before')
    @classmethod
    def coerce_option_id(cls, v):
        """Coerce selected_option_id to integer or None."""
        if v is None or v == '' or v == 'null' or v == 'undefined':
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            raise ValueError(f"Must be a valid integer or null, got: {v}")

    @field_validator('selected_option_ids', mode='before')
    @classmethod
    def coerce_option_ids_list(cls, v):
        """Coerce selected_option_ids to list of integers."""
        if v is None or v == '' or v == 'null':
            return None
        if not isinstance(v, list):
            raise ValueError(f"Must be a list, got: {type(v)}")
        try:
            return [int(item) for item in v if item is not None]
        except (ValueError, TypeError) as e:
            raise ValueError(f"All items must be valid integers: {e}")

    @field_validator('matching_pairs', mode='before')
    @classmethod
    def coerce_matching_pairs(cls, v):
        """Coerce matching_pairs to dict with integer values."""
        if v is None or v == '' or v == 'null':
            return None
        if not isinstance(v, dict):
            raise ValueError(f"Must be a dictionary, got: {type(v)}")
        try:
            return {str(k): int(v) for k, v in v.items() if v is not None}
        except (ValueError, TypeError) as e:
            raise ValueError(f"All values must be valid integers: {e}")

    @field_validator('answer_text', mode='before')
    @classmethod
    def coerce_answer_text(cls, v):
        """Coerce answer_text to string."""
        if v is None or v == 'null' or v == 'undefined':
            return None
        return str(v)


class AnswerResponse(BaseModel):
    """Response after submitting answer."""
    status: str = "saved"
    question_id: int
    message: str = "Jawaban berhasil disimpan"


class AutoSaveRequest(BaseModel):
    """
    Schema for auto-save request.
    Supports all question types: single choice (int), multiple choice (list), text, true_false_table.
    """
    session_id: int
    answers: Dict[int, Any]  # question_id -> answer_data (int, list, dict for statement_answers)
    timestamp: datetime

    @field_validator('session_id', mode='before')
    @classmethod
    def coerce_session_id(cls, v):
        """Coerce session_id to integer."""
        try:
            return int(v)
        except (ValueError, TypeError):
            raise ValueError(f"session_id must be a valid integer, got: {v}")
    
    @field_validator('answers', mode='before')
    @classmethod
    def coerce_answers_keys(cls, v):
        """Ensure all answer keys (question_ids) are integers."""
        if not isinstance(v, dict):
            raise ValueError(f"answers must be a dictionary, got: {type(v)}")
        try:
            # Convert string keys to integers, keep values as-is
            return {int(k): val for k, val in v.items()}
        except (ValueError, TypeError) as e:
            raise ValueError(f"All answer keys must be valid integers: {e}")


class AutoSaveResponse(BaseModel):
    """Response for auto-save."""
    status: str = "success"
    saved_count: int
    timestamp: datetime


class AnswerJournalEvent(BaseModel):
    """Append-only answer journal event from mobile client."""

    event_id: str = Field(..., min_length=10, max_length=120)
    sequence: int = Field(..., ge=1)
    question_id: int = Field(..., ge=1)
    local_timestamp_ms: int = Field(..., ge=1)
    selected_option_id: Optional[int] = None
    selected_option_ids: Optional[List[int]] = None
    answer_text: Optional[str] = None
    statement_answers: Optional[Dict[str, bool]] = None
    answer_metadata: Optional[Dict[str, Any]] = None

    @field_validator("event_id", mode="before")
    @classmethod
    def normalize_event_id(cls, value):
        if value is None:
            raise ValueError("event_id is required")
        normalized = str(value).strip().lower()
        if len(normalized) < 10:
            raise ValueError("event_id too short")
        return normalized

    @field_validator("question_id", "sequence", "local_timestamp_ms", mode="before")
    @classmethod
    def coerce_required_int(cls, value):
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ValueError(f"must be a valid integer, got: {value}")

    @field_validator("selected_option_id", mode="before")
    @classmethod
    def coerce_selected_option_id(cls, value):
        if value in (None, "", "null", "undefined"):
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ValueError(f"selected_option_id must be integer or null, got: {value}")

    @field_validator("selected_option_ids", mode="before")
    @classmethod
    def coerce_selected_option_ids(cls, value):
        if value in (None, "", "null"):
            return None
        if not isinstance(value, list):
            raise ValueError("selected_option_ids must be a list")
        converted = []
        for item in value:
            if item in (None, "", "null"):
                continue
            converted.append(int(item))
        return converted


class AnswerJournalSyncRequest(BaseModel):
    """Batch sync request for answer journal events."""

    session_id: int
    events: List[AnswerJournalEvent] = Field(default_factory=list, max_length=250)

    @field_validator("session_id", mode="before")
    @classmethod
    def coerce_session_id(cls, value):
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ValueError(f"session_id must be a valid integer, got: {value}")


class AnswerJournalAck(BaseModel):
    """Per-event acknowledgement response."""

    event_id: str
    question_id: Optional[int] = None
    status: Literal["applied", "duplicate", "invalid"]
    reason: Optional[str] = None


class AnswerJournalSyncResponse(BaseModel):
    """Response for journal sync with idempotent acknowledgements."""

    status: str = "ok"
    accepted: int = 0
    duplicates: int = 0
    invalid: int = 0
    applied_question_count: int = 0
    acks: List[AnswerJournalAck] = Field(default_factory=list)
    server_time: datetime = Field(default_factory=datetime.utcnow)


class ExamSubmitRequest(BaseModel):
    """Schema for submitting entire exam."""
    session_id: int
    force_submit: bool = False  # True if auto-submitted due to violations

    @field_validator('session_id', mode='before')
    @classmethod
    def coerce_session_id(cls, v):
        """Coerce session_id to integer."""
        try:
            return int(v)
        except (ValueError, TypeError):
            raise ValueError(f"session_id must be a valid integer, got: {v}")


class ExamSubmitResponse(BaseModel):
    """Response after exam submission."""
    session_id: int
    status: str
    score: Optional[float] = None
    total_points: Optional[float] = None  # FIX: Must be Optional for show_results=false
    points_earned: Optional[float] = None  # FIX: Must be Optional for show_results=false
    percentage: Optional[float] = None  # FIX: Must be Optional for show_results=false
    passed: Optional[bool] = None
    message: str


class ViolationLog(BaseModel):
    """Schema for logging violations."""
    session_id: int
    exam_id: int
    event_type: str
    event_data: Dict[str, Any]
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_agent: str
    screen_resolution: str


class ViolationResponse(BaseModel):
    """Response for violation log."""
    status: str = "logged"
    violation_count: int
    warning: Optional[str] = None


class SessionStatusResponse(BaseModel):
    """Response for session status check - WITH SERVER TIME."""
    session_id: int
    status: str
    time_remaining_seconds: int
    answered_count: int
    total_questions: int
    violation_count: int
    server_time: datetime = Field(default_factory=datetime.utcnow, description="Current server time for sync")
    
    # Pause state
    is_paused: bool = False
    paused_by: Optional[str] = None
    pause_message: Optional[str] = None
    
    # Kick/termination state (for Flutter APK polling)
    kick_reason: Optional[str] = None
    emergency_exit_allowed: bool = False
    terminated_by_admin: bool = False
    session_poll_token: Optional[str] = None
    session_poll_token_expires_minutes: Optional[int] = None

