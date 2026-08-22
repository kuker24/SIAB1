"""
Pydantic schemas for Media Library.
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class MediaFileResponse(BaseModel):
    """Schema for media file response."""
    id: int
    filename: str
    original_filename: str
    file_url: str
    file_type: str
    mime_type: Optional[str] = None
    file_size: int
    width: Optional[int] = None
    height: Optional[int] = None
    uploaded_by: Optional[int] = None
    uploader_name: Optional[str] = None
    created_at: datetime
    tags: Optional[List[str]] = []
    description: Optional[str] = None
    usage_count: int = 0
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MediaFileUpdate(BaseModel):
    """Schema for updating media metadata."""
    tags: Optional[List[str]] = None
    description: Optional[str] = None


class MediaListResponse(BaseModel):
    """Schema for media list response."""
    files: List[MediaFileResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class MediaStatsResponse(BaseModel):
    """Schema for media library statistics."""
    by_type: List[dict]
    total_files: int
    total_size_bytes: int
    total_size_mb: float
    top_tags: List[dict]
