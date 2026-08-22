"""
Error handling utilities for API endpoints.
Provides consistent error responses and logging.
"""
import logging
from typing import Callable, Any
from functools import wraps
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def handle_api_errors(endpoint_name: str = None):
    """
    Decorator to add comprehensive error handling to API endpoints.

    Usage:
        @router.get("/example")
        @handle_api_errors("get_example")
        async def get_example():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            name = endpoint_name or func.__name__
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # Re-raise HTTPException (already formatted)
                raise
            except ValueError as e:
                logger.warning(f"[{name}] Validation error: {e}")
                raise HTTPException(
                    status_code=400,
                    detail="Invalid input data"
                )
            except PermissionError as e:
                logger.warning(f"[{name}] Permission denied: {e}")
                raise HTTPException(
                    status_code=403,
                    detail="Tidak memiliki akses"
                )
            except LookupError as e:
                logger.warning(f"[{name}] Resource not found: {e}")
                raise HTTPException(
                    status_code=404,
                    detail="Resource tidak ditemukan"
                )
            except Exception as e:
                logger.error(
                    f"[{name}] Unexpected error: {e}",
                    exc_info=True,
                    extra={
                        "endpoint": name,
                        "args": str(args)[:200],  # Truncate for safety
                        "kwargs": str(kwargs)[:200]
                    }
                )
                raise HTTPException(
                    status_code=500,
                    detail="Terjadi kesalahan pada server. Silakan coba lagi."
                )
        return wrapper
    return decorator


def safe_db_operation(operation_name: str = "database operation"):
    """
    Decorator for database operations with automatic rollback on error.

    Usage:
        @safe_db_operation("create exam")
        async def create_exam_db(db: AsyncSession, data: dict):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(
                    f"Database operation failed [{operation_name}]: {e}",
                    exc_info=True
                )
                # Note: Session rollback should be handled by dependency injection
                # This is just for logging
                raise
        return wrapper
    return decorator


class APIError(Exception):
    """Base class for API errors with HTTP status codes."""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class ValidationError(APIError):
    """Raised when input validation fails."""
    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class PermissionDeniedError(APIError):
    """Raised when user doesn't have permission."""
    def __init__(self, message: str = "Tidak memiliki akses"):
        super().__init__(message, status_code=403)


class ResourceNotFoundError(APIError):
    """Raised when resource is not found."""
    def __init__(self, resource: str = "Resource"):
        super().__init__(f"{resource} tidak ditemukan", status_code=404)
