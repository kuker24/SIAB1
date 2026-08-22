"""
Notification model for in-app notifications (NO EMAIL/PUSH).
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class Notification(Base):
    """Model for in-app notifications."""
    
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False)  # exam_published, exam_graded, violation_detected, etc.
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSONB, default={})
    is_read = Column(Boolean, default=False)
    read_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))
    action_url = Column(Text)
    priority = Column(String(20), default='normal')  # low, normal, high, urgent
    
    # Relationships
    user = relationship("User", lazy="selectin")
    
    def __repr__(self):
        return f"<Notification(id={self.id}, type={self.type}, user_id={self.user_id})>"


async def create_notification(
    db,
    user_id: int,
    type: str,
    title: str,
    message: str,
    data: dict = None,
    action_url: str = None,
    priority: str = 'normal'
):
    """
    Helper function to create notification.
    
    Types:
    - exam_published: New exam available
    - exam_graded: Exam has been graded
    - violation_detected: Security violation recorded
    - exam_starting_soon: Exam reminder
    - grade_updated: Grade has been updated
    
    Note: Caller must commit the transaction.
    """
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        data=data or {},
        action_url=action_url,
        priority=priority
    )
    db.add(notification)
    return notification
