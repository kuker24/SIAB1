"""
Subject model for exam categorization.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Subject(Base):
    """Subject/Bidang Studi model for exam categorization."""
    
    __tablename__ = "subjects"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    creator = relationship("User", backref="created_subjects", lazy="selectin")
    
    def __repr__(self):
        return f"<Subject {self.name}>"
