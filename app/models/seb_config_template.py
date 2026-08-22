"""
SEB Config Template Model
Reusable configuration templates for SEB Builder
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class SebConfigTemplate(Base):
    __tablename__ = "seb_config_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)

    # Configuration preset
    config_data = Column(JSONB, nullable=False, default={})
    preset_type = Column(String(50), default="custom", index=True)  # strict, standard, permissive, custom

    # Visibility
    is_default = Column(Boolean, default=False, index=True)
    is_public = Column(Boolean, default=False)

    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now())  # Indonesia local time (WIB)
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())  # Indonesia local time (WIB)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    def to_dict(self):
        """Convert model to dictionary for API responses - safe for async"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "config_data": self.config_data,
            "preset_type": self.preset_type,
            "is_default": self.is_default,
            "is_public": self.is_public,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "creator_name": self.creator.full_name if self.creator else "System"
        }
