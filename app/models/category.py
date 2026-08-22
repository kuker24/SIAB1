from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class QuestionCategory(Base):
    __tablename__ = "question_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey("question_categories.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    parent = relationship("QuestionCategory", remote_side=[id], backref="children")
    questions = relationship("Question", back_populates="category")

    def __repr__(self):
        return f"<QuestionCategory(id={self.id}, name='{self.name}')>"
