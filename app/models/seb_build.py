"""
SEB Build Model
Tracks SEB configuration file builds for PC platforms (Windows/Mac/Linux)
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class SebBuild(Base):
    __tablename__ = "seb_builds"

    id = Column(Integer, primary_key=True, index=True)
    build_name = Column(String(200), nullable=False)
    platform = Column(String(20), default="all", nullable=False)  # windows, mac, linux, all

    # Configuration
    start_url = Column(Text, nullable=False)
    config_data = Column(JSONB, nullable=False, default={})
    config_key = Column(String(255))
    browser_exam_key = Column(String(255))

    # Admin passwords (hashed)
    admin_password_hash = Column(String(255))
    quit_password_hash = Column(String(255))

    # Build output
    file_path = Column(String(255))
    file_size = Column(BigInteger)
    status = Column(String(20), default="pending", index=True)  # pending, building, success, failed
    error_message = Column(Text)

    # Tracking
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now())  # Indonesia local time (WIB)
    completed_at = Column(DateTime)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        # Safely access creator without triggering lazy load in async context
        try:
            creator_name = self.creator.full_name if hasattr(self, '__dict__') and 'creator' in self.__dict__ and self.creator else None
        except:
            creator_name = None

        return {
            "id": self.id,
            "build_name": self.build_name,
            "platform": self.platform,
            "start_url": self.start_url,
            "config_data": self.config_data,
            "config_key": self.config_key,
            "browser_exam_key": self.browser_exam_key,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "status": self.status,
            "error_message": self.error_message,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "creator_name": creator_name,
            "download_url": f"/api/v1/seb-builder/download/{self.id}" if self.status == "success" else None
        }
