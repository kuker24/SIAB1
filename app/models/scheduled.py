"""
Scheduled Publication model for auto-publish/unpublish scheduling.
"""
from sqlalchemy import Column, Integer, String, ForeignKey, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class ScheduledPublication(Base):
    """Model for scheduled exam publications."""
    
    __tablename__ = "scheduled_publications"
    
    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id", ondelete="CASCADE"), nullable=False)
    publish_at = Column(TIMESTAMP(timezone=True), nullable=False)
    unpublish_at = Column(TIMESTAMP(timezone=True), nullable=True)
    status = Column(String(20), default="pending")  # pending, published, unpublished, cancelled
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))
    executed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Relationships
    exam = relationship("Exam", back_populates="schedules", lazy="selectin")
    creator = relationship("User", lazy="selectin")
    
    def __repr__(self):
        return f"<ScheduledPublication(id={self.id}, exam_id={self.exam_id}, status={self.status})>"
