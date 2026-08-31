"""
User model for authentication and authorization.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from app.core.roles import (
    is_admin_scope_role,
    is_gurupengawas_role,
    is_participant_role,
    is_teacher_scope_role,
)


class User(Base):
    """User model with role-based access control."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="student")
    student_class = Column(String(50), nullable=True)  # e.g., "XII-IPA-1"
    job_title = Column(String(100), nullable=True)     # e.g., "Kepala Sekolah"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    profile_picture = Column(String(255), nullable=True)

    # Relationships
    created_exams = relationship("Exam", back_populates="creator", foreign_keys="Exam.creator_id", lazy="selectin")
    exam_sessions = relationship("ExamSession", back_populates="user", lazy="selectin")

    def __repr__(self):
        return f"<User {self.username} ({self.role})>"

    @property
    def is_admin(self) -> bool:
        return is_admin_scope_role(self.role)

    @property
    def is_teacher(self) -> bool:
        return is_teacher_scope_role(self.role)

    @property
    def is_student(self) -> bool:
        return is_participant_role(self.role)

    @property
    def is_pengawas(self) -> bool:
        return is_gurupengawas_role(self.role)
