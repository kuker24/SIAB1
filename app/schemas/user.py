"""
User Pydantic schemas for request/response validation.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    """Base user schema."""
    username: str = Field(..., min_length=3, max_length=100)
    full_name: str = Field(..., min_length=1, max_length=255)


class UserCreate(UserBase):
    """Schema for user registration."""
    password: str = Field(..., min_length=6)
    role: str = Field(default="student", pattern="^(developer|admin|teacher|student|guruplus)$")
    student_class: Optional[str] = None  # e.g., "XII-IPA-1"
    job_title: Optional[str] = None      # e.g., "Kepala Sekolah"


class UserUpdate(BaseModel):
    """Schema for updating user."""
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    password: Optional[str] = None  # No min_length here, we validate in endpoint
    role: Optional[str] = Field(None, pattern="^(developer|admin|teacher|student|guruplus)$")
    student_class: Optional[str] = None
    job_title: Optional[str] = None
    is_active: Optional[bool] = None
    profile_picture: Optional[str] = None
    id: Optional[int] = None  # Ignore id if sent from frontend


class UserLogin(BaseModel):
    """Schema for user login."""
    username: str
    password: str
    # CAPTCHA fields (optional, required after 3 failed attempts)
    captcha_id: Optional[str] = None
    captcha_answer: Optional[str] = None
    # APK build token for version control (required for students on mobile)
    build_token: Optional[str] = None


class UserResponse(UserBase):
    """Schema for user response."""
    id: int
    role: str
    student_class: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    profile_picture: Optional[str] = None
    job_title: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    """JWT token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class TokenData(BaseModel):
    """Token payload data."""
    user_id: int
    username: str
    role: str
    full_name: Optional[str] = None
    student_class: Optional[str] = None
    job_title: Optional[str] = None
    is_active: Optional[bool] = None


# === NEW SCHEMAS FOR SPRINT 1.2 ===

class UserSearchFilters(BaseModel):
    """Filters for advanced user search."""
    role: Optional[str] = None
    student_class: Optional[str] = None
    is_active: Optional[bool] = None
    search_query: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    sort_by: str = "created_at"
    sort_order: str = "desc"


class UserBatchUpdate(BaseModel):
    """Schema for batch update."""
    user_ids: List[int]
    update_data: Dict[str, Any]


class UserActivityLog(BaseModel):
    """Schema for user activity log."""
    id: int
    user_id: Optional[int]
    event_type: str
    event_data: Dict[str, Any]
    ip_address: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
