"""
Exam Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
import pytz


# ============== QUESTION SETTINGS ==============

class QuestionSettings(BaseModel):
    """Flexible settings for different question types."""
    model_config = ConfigDict(extra="allow")
    # Media settings
    video_url: Optional[str] = None  # YouTube video URL

    # HOTS mode
    is_hots_mode: bool = False

    # Multiple choice complex settings
    min_correct: Optional[int] = None  # Minimum correct answers required
    max_correct: Optional[int] = None  # Maximum correct answers allowed
    partial_scoring: bool = False      # Enable proportional scoring

    # Short answer settings
    case_sensitive: bool = False
    exact_match: bool = False
    acceptable_answers: List[str] = []  # List of accepted answers

    # True/False Table settings (for multiple_choice_complex subtype)
    correct_statements: Dict[str, bool] = {}  # {statement_id: true/false}

    # Table Validation (PGK Type B) settings
    statements: List[str] = []  # List of statement texts for table validation
    statement_answers: List[bool] = []  # List of correct answers (true/false) for each statement

    # Combination format settings (for multiple_choice_complex subtype)
    # Uses regular options with is_correct flag

    # Essay settings
    min_words: Optional[int] = None
    max_words: Optional[int] = None


# ============== QUESTION OPTIONS ==============

class QuestionOptionCreate(BaseModel):
    """Schema for creating question option."""
    option_text: str
    is_correct: Optional[bool] = False  # Optional for matching type
    order_index: int
    option_group: str = "standard"      # 'standard', 'left', 'right' for matching
    pair_id: Optional[str] = None       # Links left to right in matching


class QuestionOptionResponse(BaseModel):
    """Schema for question option response - WITHOUT is_correct for students!"""
    id: int
    option_text: str
    order_index: int
    option_group: str = "standard"  # Needed for matching rendering
    pair_id: Optional[str] = None   # FIX: Critical for matching questions!

    model_config = ConfigDict(from_attributes=True)


class QuestionOptionFullResponse(QuestionOptionResponse):
    """Full response including is_correct - for teachers/admin only."""
    is_correct: Optional[bool] = None
    pair_id: Optional[str] = None


# ============== QUESTIONS ==============

# Valid question types (matching removed, complex subtypes added)
QUESTION_TYPES = [
    "multiple_choice",          # Single correct answer
    "multiple_choice_complex",  # Multiple correct (HOTS) - subtypes: checkbox, true_false_table, combination
    "true_false",
    "essay",
    "short_answer",             # Isian singkat
]
QUESTION_TYPE_PATTERN = "^(" + "|".join(QUESTION_TYPES) + ")$"


from app.schemas.question_bank import CategoryResponse, TagResponse

class QuestionCreate(BaseModel):
    """Schema for creating question."""
    question_text: str
    stimulus: Optional[str] = None  # Optional context/reading for PGK or HOTS questions
    question_type: str = Field(
        default="multiple_choice",
        pattern=QUESTION_TYPE_PATTERN
    )
    question_subtype: Optional[str] = None
    pgk_type: Optional[str] = "checkbox"  # NEW: PGK sub-type ('checkbox' or 'table_validation')
    difficulty_level: str = "medium"
    category_id: Optional[int] = None
    tag_ids: List[int] = []

    question_settings: QuestionSettings = QuestionSettings()
    points: Decimal = Field(default=Decimal("1.00"), ge=0)
    order_index: int
    image_url: Optional[str] = None
    video_url: Optional[str] = None  # YouTube or video hosting URL
    audio_url: Optional[str] = None  # Audio file URL
    options: List[QuestionOptionCreate] = []


class QuestionResponse(BaseModel):
    """Schema for question response - WITHOUT correct answers!"""
    id: int
    question_text: str
    stimulus: Optional[str] = None  # NEW: Context/reading for HOTS/AKM questions
    question_type: str
    pgk_type: Optional[str] = None  # NEW: PGK sub-type
    difficulty_level: str = "medium"
    category: Optional[CategoryResponse] = None
    tags: List[TagResponse] = []

    question_settings: Optional[Dict[str, Any]] = {}  # Needed for frontend rendering hints
    points: Decimal
    order_index: int
    image_url: Optional[str] = None
    video_url: Optional[str] = None  # FIX: YouTube video URL for questions
    audio_url: Optional[str] = None  # FIX: Audio file URL for questions
    options: List[QuestionOptionResponse] = []

    model_config = ConfigDict(from_attributes=True)


class QuestionFullResponse(QuestionResponse):
    """Full question response with correct answers - for teachers/admin."""
    options: List[QuestionOptionFullResponse] = []


class ExamCreate(BaseModel):
    """Schema for creating exam."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    duration_minutes: int = Field(..., gt=0)
    start_time: datetime
    end_time: datetime
    passing_score: Optional[Decimal] = Field(None, ge=0, le=100)
    max_attempts: int = Field(default=1, ge=1)
    shuffle_questions: bool = False
    shuffle_options: bool = False
    show_results: bool = False
    allow_review: bool = False
    is_published: bool = False
    subject: Optional[str] = None  # Bidang Studi / Mata Pelajaran
    exam_type: Optional[str] = None  # Tipe Ujian (Harian, Mingguan, UTS, etc.)
    academic_year: Optional[str] = None  # Tahun Ajaran (e.g., 2024/2025)
    show_teacher_name: bool = True  # Display teacher name on exam
    builder_settings: Dict[str, Any] = Field(default_factory=dict)  # UI defaults for question authoring
    allowed_classes: Optional[str] = None  # Comma-separated class names
    allowed_students: Optional[str] = None  # Comma-separated user IDs


class ExamResponse(BaseModel):
    """Schema for exam response."""
    id: int
    title: str
    description: Optional[str] = None
    creator_id: int
    duration_minutes: int
    start_time: datetime
    end_time: datetime
    start_time_wib: str  # Formatted WIB time
    end_time_wib: str    # Formatted WIB time
    passing_score: Optional[Decimal] = None
    max_attempts: int
    shuffle_questions: bool
    shuffle_options: bool
    show_results: bool
    allow_review: bool
    is_published: bool
    access_token: Optional[str] = None  # 6-char exam token
    subject: Optional[str] = None  # Bidang Studi / Mata Pelajaran
    exam_type: Optional[str] = None  # Tipe Ujian (Harian, Mingguan, UTS, etc.)
    academic_year: Optional[str] = None  # Tahun Ajaran (e.g., 2024/2025)
    show_teacher_name: bool = True  # Display teacher name on exam
    builder_settings: Dict[str, Any] = Field(default_factory=dict)
    teacher_name: Optional[str] = None  # Creator's full name
    allowed_classes: Optional[str] = None  # Comma-separated class names
    allowed_students: Optional[str] = None  # Comma-separated user IDs
    question_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_wib(cls, exam):
        """Create response with WIB timezone - no conversion needed since all times are WIB."""
        # Format time directly without conversion (times are already in WIB)
        def format_wib(dt):
            if dt is None:
                return ""
            # Handle naive datetime (no timezone info) - assume it's already WIB
            if dt.tzinfo is None:
                return dt.strftime('%d %B %Y %H:%M WIB')
            # If has timezone, convert to WIB
            wib = pytz.timezone('Asia/Jakarta')
            return dt.astimezone(wib).strftime('%d %B %Y %H:%M WIB')

        precomputed_question_count = getattr(exam, "_question_count", None)
        if precomputed_question_count is None:
            precomputed_question_count = len(exam.questions) if exam.questions else 0

        return cls(
            id=exam.id,
            title=exam.title,
            description=exam.description,
            creator_id=exam.creator_id,
            duration_minutes=exam.duration_minutes,
            start_time=exam.start_time,
            end_time=exam.end_time,
            start_time_wib=format_wib(exam.start_time),
            end_time_wib=format_wib(exam.end_time),
            passing_score=exam.passing_score,
            max_attempts=exam.max_attempts,
            shuffle_questions=exam.shuffle_questions,
            shuffle_options=exam.shuffle_options,
            show_results=exam.show_results,
            allow_review=exam.allow_review,
            is_published=exam.is_published,
            access_token=exam.access_token,
            subject=exam.subject,
            exam_type=exam.exam_type,
            academic_year=exam.academic_year,
            show_teacher_name=exam.show_teacher_name if exam.show_teacher_name is not None else True,
            builder_settings=exam.builder_settings or {},
            teacher_name=exam.creator.full_name if exam.creator else None,
            allowed_classes=exam.allowed_classes,
            allowed_students=exam.allowed_students,
            question_count=precomputed_question_count,
            created_at=exam.created_at,
        )


class ExamListResponse(BaseModel):
    """Schema for exam list response."""
    exams: List[ExamResponse]
    total: int


class ExamStartResponse(BaseModel):
    """Response when starting an exam session."""
    session_id: int
    exam_id: int
    exam_title: str
    duration_minutes: int
    question_count: int
    start_time: datetime
    end_time: datetime
    server_time: datetime  # Server's current time for anti-cheat synchronization
    show_results: bool
    show_teacher_name: bool = True
    teacher_name: Optional[str] = None
    # Exam metadata for display
    subject: Optional[str] = None  # Bidang Studi / Mata Pelajaran
    exam_type: Optional[str] = None  # Tipe Ujian (Harian, UTS, UAS, etc.)
    shuffle_questions: bool = False
    shuffle_options: bool = False
    session_poll_token: Optional[str] = None
    session_poll_token_expires_minutes: Optional[int] = None
    questions: List[QuestionResponse]


class SEBLaunchResponse(BaseModel):
    """Response for SEB mobile launch."""
    launch_url: str
    display_text: str
    instructions: str


# ============== NEW SCHEMAS FOR SPRINT 1.3 ==============

class ExamTemplateCreate(BaseModel):
    """Schema for creating an exam template."""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    template_data: Dict[str, Any]  # JSON of exam settings & questions
    is_public: bool = False


class ExamTemplateResponse(BaseModel):
    """Response schema for exam templates."""
    id: int
    name: str
    description: Optional[str]
    creator_id: int
    is_public: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExamAnalytics(BaseModel):
    """Comprehensive exam analytics."""
    exam_id: int
    total_participants: int
    active_sessions: int
    completed_sessions: int
    average_score: float
    highest_score: float
    lowest_score: float
    pass_rate: float  # Percentage

    # Advanced stats
    score_distribution: Dict[str, int]  # e.g., "0-20": 5, "21-40": 10
    difficult_questions: List[Dict[str, Any]]  # Top 5 hardest questions
    violation_stats: Dict[str, int]  # Count of different violations
