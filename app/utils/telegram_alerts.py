"""
Telegram Alert System for Security Events
Enhanced version with proper async support and config integration
"""
import httpx
import logging
from datetime import datetime, timezone, timedelta
from app.config import settings

logger = logging.getLogger(__name__)


async def send_security_alert(event) -> bool:
    """
    Send security alert to Telegram

    Args:
        event: SecurityEvent instance

    Returns:
        bool: True if sent successfully
    """
    if not settings.telegram_alerting_active:
        logger.debug("Telegram alerts disabled")
        return False

    if not settings.telegram_bot_token or not settings.telegram_chat_ids:
        logger.warning("Telegram not configured properly")
        return False

    try:
        message = format_security_message(event)

        url = f'https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage'
        success_count = 0

        async with httpx.AsyncClient(timeout=10.0) as client:
            for chat_id in settings.telegram_chat_ids_list:
                try:
                    response = await client.post(
                        url,
                        data={
                            'chat_id': chat_id,
                            'text': message,
                            'parse_mode': 'HTML'
                        }
                    )

                    if response.status_code == 200:
                        success_count += 1
                        logger.info(f"Security alert sent to Telegram chat {chat_id}")
                    else:
                        logger.error(
                            f"Failed to send alert to {chat_id}: "
                            f"Status {response.status_code}, Response: {response.text}"
                        )
                except Exception as e:
                    logger.error(f"Error sending to {chat_id}: {str(e)}")

        return success_count > 0

    except Exception as e:
        logger.error(f"Failed to send Telegram security alert: {e}")
        return False


def format_security_message(event) -> str:
    """
    Format security event as Telegram message

    Args:
        event: SecurityEvent instance

    Returns:
        Formatted message string (HTML)
    """
    severity_emoji = {
        'low': '⚠️',
        'medium': '🟡',
        'high': '🟠',
        'critical': '🚨'
    }

    emoji = severity_emoji.get(event.severity, '⚠️')

    # Get time in WIB (UTC+7)
    wib_tz = timezone(timedelta(hours=7))
    event_time = event.timestamp.astimezone(wib_tz) if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc).astimezone(wib_tz)

    message = f"""
{emoji} <b>SECURITY ALERT</b>

<b>Event:</b> {event.event_type.upper().replace('_', ' ')}
<b>Severity:</b> {event.severity.upper()}
<b>Time:</b> {event_time.strftime('%Y-%m-%d %H:%M:%S')} WIB

<b>Details:</b>
IP: {event.ip_address}
User ID: {event.user_id or 'Unknown'}
Session ID: {event.session_id or 'N/A'}
Endpoint: {event.endpoint}

<b>App Info:</b>
Signature: {event.app_signature[:16]}...
Version: {event.app_version or 'Unknown'}

<b>User Agent:</b>
{event.user_agent[:100]}...
"""

    if event.event_type == 'invalid_signature':
        message += "\n⚠️ <b>TAMPERED APK DETECTED!</b>"

    return message.strip()


async def send_lockout_alert(username: str, ip_address: str, attempts: int = 5) -> bool:
    """
    Send account lockout alert to Telegram

    Args:
        username: Username that was locked
        ip_address: IP address of login attempts
        attempts: Number of failed attempts (default: 5)

    Returns:
        bool: True if sent successfully
    """
    if not settings.telegram_alerting_active:
        return False

    # Get current time in WIB
    wib_tz = timezone(timedelta(hours=7))
    current_time = datetime.now(timezone.utc).astimezone(wib_tz)
    timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")

    message = f"""
🔒 <b>ACCOUNT LOCKOUT ALERT</b>

<b>Username:</b> {username}
<b>IP Address:</b> {ip_address}
<b>Failed Attempts:</b> {attempts}
<b>Time:</b> {timestamp} WIB
<b>Lockout Duration:</b> 15 minutes

⚠️ <b>Action Required:</b>
Monitor for suspicious activity. Account can be unlocked manually via Security Dashboard if needed.
"""

    try:
        url = f'https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage'
        success_count = 0

        async with httpx.AsyncClient(timeout=10.0) as client:
            for chat_id in settings.telegram_chat_ids_list:
                try:
                    response = await client.post(
                        url,
                        data={
                            'chat_id': chat_id,
                            'text': message,
                            'parse_mode': 'HTML'
                        }
                    )

                    if response.status_code == 200:
                        success_count += 1
                        logger.info(f"Lockout alert sent to Telegram chat {chat_id}")
                except Exception as e:
                    logger.error(f"Error sending lockout alert to {chat_id}: {str(e)}")

        return success_count > 0

    except Exception as e:
        logger.error(f"Failed to send lockout alert: {e}")
        return False


async def send_test_alert() -> tuple[bool, str]:
    """
    Send test alert to verify Telegram integration

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not settings.telegram_alerting_active:
        return False, "Telegram alerts are disabled"

    if not settings.telegram_bot_token or not settings.telegram_chat_ids:
        return False, "Telegram credentials not configured"

    try:
        url = f'https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage'

        # Get current time in WIB
        wib_tz = timezone(timedelta(hours=7))
        current_time = datetime.now(timezone.utc).astimezone(wib_tz)
        timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")

        message = f"""
✅ <b>Test Alert - Ujian Online System</b>

<b>Status:</b> Telegram notifications are working correctly!
<b>Time:</b> {timestamp} WIB

📊 <b>Configured Recipients:</b> {len(settings.telegram_chat_ids_list)}

System is ready to send:
• 🔒 Account lockout alerts
• 🚨 Security event notifications
• 🛠️ Maintenance notifications
• 📝 Exam event updates
"""

        success_count = 0
        async with httpx.AsyncClient(timeout=10.0) as client:
            for chat_id in settings.telegram_chat_ids_list:
                try:
                    response = await client.post(
                        url,
                        data={
                            'chat_id': chat_id,
                            'text': message,
                            'parse_mode': 'HTML'
                        }
                    )

                    if response.status_code == 200:
                        success_count += 1
                    else:
                        logger.error(f"Failed to send to {chat_id}: {response.text}")
                except Exception as e:
                    logger.error(f"Error sending test to {chat_id}: {str(e)}")

        if success_count > 0:
            return True, f"Test alert sent successfully to {success_count} recipient(s)"
        else:
            return False, "Failed to send to any recipients"

    except Exception as e:
        return False, f"Error: {str(e)}"
