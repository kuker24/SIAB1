"""
Pydantic schemas for Scheduled Publications.
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone
from typing import Optional


class ScheduleCreate(BaseModel):
    """Schema for creating scheduled publication."""
    publish_at: datetime = Field(..., description="When to auto-publish exam")
    unpublish_at: Optional[datetime] = Field(None, description="When to auto-unpublish exam (optional)")
    
    @field_validator('publish_at')
    @classmethod
    def publish_must_be_future(cls, v):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        if v <= datetime.now(timezone.utc):
            raise ValueError('Publish time must be in the future')
        return v
    
    @field_validator('unpublish_at')
    @classmethod
    def unpublish_must_be_after_publish(cls, v, info):
        if v is None:
            return v
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        publish_at = info.data.get('publish_at')
        if publish_at and v <= publish_at:
            raise ValueError('Unpublish time must be after publish time')
        return v


class ScheduleResponse(BaseModel):
    """Schema for schedule response."""
    id: int
    exam_id: int
    publish_at: datetime
    unpublish_at: Optional[datetime] = None
    status: str
    created_by: Optional[int] = None
    created_at: datetime
    executed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True


class ScheduleListResponse(BaseModel):
    """Schema for list of schedules response."""
    schedules: list[ScheduleResponse]
    total: int
