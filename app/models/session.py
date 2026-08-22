"""
ExamSession, Answer, and ExamLog models.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, ARRAY
from sqlalchemy.orm import relationship
from app.database import Base


class ExamSession(Base):
    """Exam session model for tracking student exam attempts."""

    __tablename__ = "exam_sessions"
    __table_args__ = (
        Index(
            "ix_exam_sessions_active_user_exam_unique",
            "user_id",
            "exam_id",
            unique=True,
            postgresql_where=text("status IN ('in_progress', 'active')"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="in_progress")  # in_progress, completed, submitted, abandoned
    score = Column(Numeric(5, 2), nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    seb_detected = Column(Boolean, default=False)
    is_secure_app_verified = Column(Boolean, default=False)
    violation_count = Column(Integer, default=0)

    # Admin controls for emergency exit
    emergency_exit_allowed = Column(Boolean, default=False)  # Admin can enable emergency exit
    terminated_by_admin = Column(Boolean, default=False)     # Session forcefully terminated by admin

    # Pause functionality for network outage recovery
    is_paused = Column(Boolean, default=False)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    total_paused_seconds = Column(Integer, default=0)  # Accumulated pause time

    # Archived exam metadata - preserved when exam is deleted
    archived_exam_title = Column(String(255), nullable=True)
    archived_exam_subject = Column(String(100), nullable=True)
    archived_exam_type = Column(String(100), nullable=True)

    # Relationships
    user = relationship("User", back_populates="exam_sessions", lazy="selectin")
    exam = relationship("Exam", back_populates="sessions", lazy="selectin")
    answers = relationship("Answer", back_populates="session", lazy="selectin", cascade="all, delete-orphan")
    logs = relationship("ExamLog", back_populates="session", lazy="selectin", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ExamSession {self.id}: User {self.user_id} - Exam {self.exam_id}>"

    @property
    def is_active(self) -> bool:
        """Check if session is still active."""
        return self.status == "in_progress"

    @property
    def answered_count(self) -> int:
        """Get count of answered questions."""
        return len(self.answers)


class Answer(Base):
    """Answer model for student responses - supports all question types."""

    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_answers_session_question"),
    )

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)

    # Single selection (multiple_choice, true_false)
    selected_option_id = Column(Integer, ForeignKey("question_options.id"), nullable=True)

    # Multiple selections (multiple_choice_complex)
    selected_option_ids = Column(ARRAY(Integer), nullable=True)

    # Legacy field - kept for backward compatibility but no longer used
    matching_pairs = Column(JSONB, nullable=True)

    # Text answer (essay, short_answer)
    answer_text = Column(Text, nullable=True)

    # Grading results
    is_correct = Column(Boolean, nullable=True)
    points_earned = Column(Numeric(5, 2), nullable=True)

    # Flexible metadata for future use
    answer_metadata = Column(JSONB, default={})

    answered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    session = relationship("ExamSession", back_populates="answers", lazy="selectin")
    question = relationship("Question", back_populates="answers", lazy="selectin")

    def __repr__(self):
        return f"<Answer {self.id}: Session {self.session_id} - Question {self.question_id}>"


class ExamLog(Base):
    """Exam log model for audit trail and violation tracking."""

    __tablename__ = "exam_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    event_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    session = relationship("ExamSession", back_populates="logs", lazy="selectin")

    def __repr__(self):
        return f"<ExamLog {self.id}: {self.event_type}>"
