"""
Standard API Response Schemas.

Provides consistent response formats across all API endpoints for:
- Success responses with data
- Error responses with details
- Paginated list responses
"""
from typing import TypeVar, Generic, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, timezone

T = TypeVar('T')


class ErrorResponse(BaseModel):
    """Standard error response format."""
    success: bool = False
    error: str = Field(..., description="Error code (e.g., 'NOT_FOUND', 'VALIDATION_ERROR')")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "NOT_FOUND",
                "message": "Ujian tidak ditemukan",
                "details": {"exam_id": 123},
                "timestamp": "2026-01-22T06:20:00Z"
            }
        }


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response format with optional data."""
    success: bool = True
    message: str = Field(..., description="Success message")
    data: Optional[T] = Field(None, description="Response data")


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""
    total: int = Field(..., description="Total number of items")
    page: int = Field(1, description="Current page number (1-indexed)")
    per_page: int = Field(20, description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")
    has_next: bool = Field(..., description="Whether there's a next page")
    has_prev: bool = Field(..., description="Whether there's a previous page")

    @classmethod
    def create(cls, total: int, page: int = 1, per_page: int = 20):
        """Factory method to create pagination meta."""
        total_pages = max(1, (total + per_page - 1) // per_page)
        return cls(
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """Standard paginated list response."""
    success: bool = True
    data: List[T] = Field(default_factory=list, description="List of items")
    meta: PaginationMeta = Field(..., description="Pagination metadata")

    @classmethod
    def create(cls, items: List[T], total: int, page: int = 1, per_page: int = 20):
        """Factory method to create paginated response."""
        return cls(
            data=items,
            meta=PaginationMeta.create(total, page, per_page)
        )


# Common error types as constants
class ErrorCodes:
    """Standard error codes."""
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    SERVER_ERROR = "SERVER_ERROR"
    DUPLICATE = "DUPLICATE"
    EXPIRED = "EXPIRED"


def create_error_response(
    error_code: str,
    message: str,
    details: Optional[dict] = None
) -> ErrorResponse:
    """Helper function to create error responses."""
    return ErrorResponse(
        error=error_code,
        message=message,
        details=details
    )
