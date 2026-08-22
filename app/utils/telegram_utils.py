"""
Telegram Notification Utilities
Send notifications to Telegram groups/channels
"""
import httpx
import logging
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from app.config import settings

logger = logging.getLogger(__name__)


async def send_telegram_notification(
    message: str,
    parse_mode: str = "Markdown",
    chat_ids: Optional[List[str]] = None
) -> bool:
    """
    Send a notification message to Telegram.
    
    Args:
        message: The message text to send (supports Markdown formatting)
        parse_mode: Message formatting mode (Markdown or HTML)
        chat_ids: Optional list of chat IDs. If None, uses config default.
    
    Returns:
        bool: True if at least one message was sent successfully
    """
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured. Skipping notification.")
        return False
    
    # Use provided chat IDs or fall back to config
    target_chat_ids = chat_ids or settings.telegram_chat_ids_list
    
    if not target_chat_ids:
        logger.warning("No Telegram chat IDs configured. Skipping notification.")
        return False
    
    telegram_api_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    success_count = 0
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for chat_id in target_chat_ids:
            try:
                response = await client.post(
                    telegram_api_url,
                    data={
                        "chat_id": chat_id,
                        "text": message,
                        "parse_mode": parse_mode
                    }
                )
                
                if response.status_code == 200:
                    success_count += 1
                    logger.info(f"Telegram notification sent successfully to chat_id: {chat_id}")
                else:
                    logger.error(
                        f"Failed to send Telegram notification to {chat_id}. "
                        f"Status: {response.status_code}, Response: {response.text}"
                    )
            except Exception as e:
                logger.error(f"Error sending Telegram notification to {chat_id}: {str(e)}")
    
    return success_count > 0


async def send_maintenance_start_notification(admin_username: str) -> bool:
    """
    Send notification when maintenance mode is activated.
    
    Args:
        admin_username: Username of admin who activated maintenance mode
    
    Returns:
        bool: True if notification sent successfully
    """
    # Get current time in WIB (UTC+7)
    wib_tz = timezone(timedelta(hours=7))
    current_time = datetime.now(timezone.utc).astimezone(wib_tz)
    timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    message = (
        "🛠️ *SISTEM SEDANG DALAM PEMELIHARAAN*\n\n"
        "⚠️ *Status*: Maintenance\n"
        f"⏰ *Time*: {timestamp}\n\n"
        "ℹ️ *Informasi*:\n"
        "• Guru dan siswa tidak dapat login\n\n"
        "Kami akan memberitahu saat pemeliharaan selesai 🔧"
    )
    
    return await send_telegram_notification(message)


async def send_maintenance_end_notification(admin_username: str) -> bool:
    """
    Send notification when maintenance mode is deactivated.
    
    Args:
        admin_username: Username of admin who deactivated maintenance mode
    
    Returns:
        bool: True if notification sent successfully
    """
    # Get current time in WIB (UTC+7)
    wib_tz = timezone(timedelta(hours=7))
    current_time = datetime.now(timezone.utc).astimezone(wib_tz)
    timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    message = (
        "✅ *PEMELIHARAAN SELESAI - SISTEM NORMAL*\n\n"
        "✓ *Status*: Maintenance Selesai\n"
        f"⏰ *Time*: {timestamp}\n\n"
        "ℹ️ *Informasi*:\n"
        "• Sistem kembali beroperasi normal\n"
        "• Guru dan siswa dapat login kembali\n"
        "• Semua fitur tersedia seperti biasa\n\n"
        "Terima kasih atas kesabaran Anda! 🎉"
    )
    
    return await send_telegram_notification(message)


async def send_system_startup_notification() -> bool:
    """
    Send notification when system starts up (after restart/redeploy).
    
    Returns:
        bool: True if notification sent successfully
    """
    # Get current time in WIB (UTC+7)
    wib_tz = timezone(timedelta(hours=7))
    current_time = datetime.now(timezone.utc).astimezone(wib_tz)
    timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    message = (
        "🚀 *SISTEM ONLINE - API STARTED*\n\n"
        "✅ *Status*: Service Running\n"
        f"⏰ *Time*: {timestamp} WIB\n"
        "🔧 *Version*: 1.0.0\n\n"
        "ℹ️ *Info*:\n"
        "• All services operational\n"
        "• Database connected\n"
        "• Redis connected\n\n"
        "System ready to serve requests 🎉"
    )
    
    return await send_telegram_notification(message)
