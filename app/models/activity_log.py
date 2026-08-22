from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


def utc_now():
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class UserActivityLog(Base):
    __tablename__ = "user_activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(50), nullable=False, index=True)
    event_data = Column(JSONB, default={})
    ip_address = Column(String(50), nullable=True)
    # Use timezone-aware UTC time
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True)

    # Relationship
    user = relationship("User", backref="activity_logs")
