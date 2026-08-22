from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

# Association Table for Many-to-Many
question_tags_map = Table(
    "question_tags_map",
    Base.metadata,
    Column("question_id", Integer, ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("question_tags.id", ondelete="CASCADE"), primary_key=True),
)

class QuestionTag(Base):
    __tablename__ = "question_tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    color = Column(String(20), default="#6c757d")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    questions = relationship("Question", secondary=question_tags_map, back_populates="tags")

    def __repr__(self):
        return f"<QuestionTag(id={self.id}, name='{self.name}')>"
