"""
Exam model with SEB configuration support.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class Exam(Base):
    """Exam model with SEB integration."""

    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=60)  # Default 60 minutes
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    passing_score = Column(Numeric(5, 2), nullable=True)
    max_attempts = Column(Integer, default=1)
    shuffle_questions = Column(Boolean, default=False)
    shuffle_options = Column(Boolean, default=False)
    show_results = Column(Boolean, default=False, nullable=False)
    allow_review = Column(Boolean, default=False)
    seb_config_key = Column(String(255), nullable=False)
    seb_browser_exam_key = Column(String(255), nullable=True)
    seb_mobile_protocol_url = Column(Text, nullable=True)
    is_published = Column(Boolean, default=False)
    access_token = Column(String(10), unique=True, nullable=True, index=True)  # 6-char exam token
    subject = Column(String(100), nullable=True)  # Bidang Studi / Mata Pelajaran
    exam_type = Column(String(100), nullable=True)  # Tipe Ujian (Harian, Mingguan, UTS, etc.)
    academic_year = Column(String(20), nullable=True)  # Tahun Ajaran (e.g., 2024/2025)
    show_teacher_name = Column(Boolean, default=True)  # Display teacher name on exam
    builder_settings = Column(JSONB, default={})  # Builder defaults (mode cepat/model/toggles)
    allowed_classes = Column(Text, nullable=True)  # Comma-separated class names, NULL = all classes
    allowed_students = Column(Text, nullable=True)  # Comma-separated user IDs, NULL = class-based rules apply

    # Global pause control (for network outages - affects ALL students in this exam)
    is_globally_paused = Column(Boolean, default=False)
    globally_paused_at = Column(DateTime(timezone=True), nullable=True)
    globally_paused_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # Admin/teacher who paused

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Soft delete support - exam results are preserved when exam is "deleted"
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Track if exam has ever received submissions
    # Used to distinguish fresh exams (show in results) from exams with deleted results (hide)
    has_ever_had_results = Column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    creator = relationship("User", back_populates="created_exams", foreign_keys=[creator_id], lazy="selectin")
    questions = relationship("Question", back_populates="exam", lazy="selectin", cascade="all, delete-orphan")
    sessions = relationship("ExamSession", back_populates="exam", lazy="selectin")
    # Do not auto-load schedules on every Exam read path; scheduling endpoints query it explicitly.
    schedules = relationship("ScheduledPublication", back_populates="exam", lazy="noload", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Exam {self.title}>"

    @property
    def is_active(self) -> bool:
        """Check if exam is currently active."""
        now = datetime.now(timezone.utc)
        return self.is_published and self.start_time <= now <= self.end_time

    @property
    def total_points(self) -> float:
        """Calculate total points for the exam."""
        return sum(q.points for q in self.questions)

    @property
    def question_count(self) -> int:
        """Get total number of questions."""
        return len(self.questions)
