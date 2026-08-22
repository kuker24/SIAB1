"""
APK Build Model
Tracks APK build history and status
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class ApkBuild(Base):
    __tablename__ = "apk_builds"

    id = Column(Integer, primary_key=True, index=True)
    app_name = Column(String(100), nullable=False)
    package_name = Column(String(100), default="com.ujianonline.seb")
    version = Column(String(20), default="1.0.0")

    # Icon
    icon_path = Column(String(255))

    # Build status: pending, building, success, failed
    status = Column(String(20), default="pending", index=True)
    build_log = Column(Text)
    error_message = Column(Text)

    # Build output
    file_path = Column(String(255))
    file_size = Column(Integer)  # bytes
    build_time_seconds = Column(Integer)

    # Tracking
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now())  # Indonesia local time (WIB)
    completed_at = Column(DateTime)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    def to_dict(self):
        return {
            "id": self.id,
            "app_name": self.app_name,
            "package_name": self.package_name,
            "version": self.version,
            "icon_path": self.icon_path,
            "status": self.status,
            "build_log": self.build_log or "",  # FIX: Handle None
            "error_message": self.error_message or "",  # FIX: Handle None
            "file_path": self.file_path,
            "file_size": self.file_size,
            "build_time_seconds": self.build_time_seconds,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "creator_name": self.creator.full_name if self.creator else "Admin",  # FIX: Safe access
            "download_url": f"/api/v1/apk-builder/download/{self.id}" if self.status == "success" else None
        }
