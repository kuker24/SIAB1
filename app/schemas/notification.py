"""
Pydantic schemas for In-App Notifications (NO EMAIL/PUSH).
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any, List


class NotificationResponse(BaseModel):
    """Schema for notification response."""
    id: int
    user_id: int
    type: str
    title: str
    message: str
    data: Dict[str, Any] = {}
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime
    action_url: Optional[str] = None
    priority: str
    
    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Schema for list of notifications response."""
    notifications: List[NotificationResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class UnreadCountResponse(BaseModel):
    """Schema for unread notification count."""
    unread_count: int
