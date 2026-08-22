from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class ExamTemplate(Base):
    __tablename__ = "exam_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    creator_id = Column(Integer, ForeignKey("users.id"))
    template_data = Column(JSONB)
    is_public = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    creator = relationship("User")
