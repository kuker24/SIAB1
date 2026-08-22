"""
Telegram Admin API - Custom Broadcast
Admin-only endpoint for sending custom Telegram notifications
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta

from app.models.user import User
from app.core.security import get_current_active_admin
from app.utils.telegram_utils import send_telegram_notification
from app.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telegram", tags=["telegram"])


class BroadcastMessage(BaseModel):
    """Request model for custom broadcast"""
    message: str = Field(..., min_length=1, max_length=2000, description="Broadcast message content")


class BroadcastResponse(BaseModel):
    """Response model for broadcast"""
    success: bool
    recipients: int
    sent_by: str
    timestamp: str


def format_admin_broadcast(message: str, admin_username: str) -> str:
    """
    Format admin broadcast message with metadata

    Args:
        message: The custom message from admin
        admin_username: Username of admin sending the broadcast

    Returns:
        Formatted message string
    """
    # Get current time in WIB (UTC+7)
    wib_tz = timezone(timedelta(hours=7))
    current_time = datetime.now(timezone.utc).astimezone(wib_tz)
    timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")

    formatted = (
        "📢 *ADMIN BROADCAST*\n\n"
        f"{message}\n\n"
        "─────────────────────\n"
        f"📤 Sent by: {admin_username}\n"
        f"⏰ Time: {timestamp} WIB"
    )

    return formatted


@router.post("/broadcast", response_model=BroadcastResponse)
async def send_custom_broadcast(
    request: BroadcastMessage,
    current_user: User = Depends(get_current_active_admin)
):
    """
    Send custom Telegram notification (admin only)

    - **message**: Custom message to broadcast (1-2000 characters)

    Returns:
        - success: Whether broadcast was sent
        - recipients: Number of recipients
        - sent_by: Admin username
        - timestamp: Send time
    """
    if not settings.telegram_alerting_active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram notifications are disabled"
        )

    if not settings.telegram_bot_token or not settings.telegram_chat_ids:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram not configured"
        )

    # Sanitize and format message
    message_text = request.message.strip()
    if not message_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty"
        )

    # Format with admin metadata
    formatted_message = format_admin_broadcast(message_text, current_user.username)

    # Send broadcast
    try:
        success = await send_telegram_notification(formatted_message, parse_mode="Markdown")

        # Log the broadcast
        logger.info(
            f"Admin broadcast sent by {current_user.username} (ID: {current_user.id}). "
            f"Success: {success}, Recipients: {len(settings.telegram_chat_ids_list)}"
        )

        # Get timestamp
        wib_tz = timezone(timedelta(hours=7))
        current_time = datetime.now(timezone.utc).astimezone(wib_tz)
        timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")

        return BroadcastResponse(
            success=success,
            recipients=len(settings.telegram_chat_ids_list),
            sent_by=current_user.username,
            timestamp=timestamp
        )

    except Exception:
        logger.exception("Failed to send admin broadcast")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send broadcast"
        )


@router.get("/status")
async def get_telegram_status(current_user: User = Depends(get_current_active_admin)):
    """
    Get Telegram integration status (admin only)

    Returns current configuration and connectivity status
    """
    return {
        "enabled": settings.telegram_alerting_active,
        "configured": bool(settings.telegram_bot_token and settings.telegram_chat_ids),
        "recipients": len(settings.telegram_chat_ids_list) if settings.telegram_chat_ids else 0,
        "bot_token_set": bool(settings.telegram_bot_token)
    }
