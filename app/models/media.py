"""
Media File model for centralized media library management.
"""
from sqlalchemy import Column, Integer, String, BigInteger, Text, ForeignKey
from sqlalchemy.dialects.postgresql import TIMESTAMP, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class MediaFile(Base):
    """Model for media library management."""
    
    __tablename__ = "media_files"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)  # UUID-based filename
    original_filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_url = Column(Text, nullable=False)
    file_type = Column(String(50), nullable=False)  # image, video, audio, document
    mime_type = Column(String(100))
    file_size = Column(BigInteger, nullable=False)
    width = Column(Integer)
    height = Column(Integer)
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    tags = Column(ARRAY(String))
    description = Column(Text)
    usage_count = Column(Integer, default=0)
    last_used_at = Column(TIMESTAMP(timezone=True))
    
    # Relationships
    uploader = relationship("User", lazy="selectin")
    
    def __repr__(self):
        return f"<MediaFile(id={self.id}, filename={self.filename}, type={self.file_type})>"
