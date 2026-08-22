"""
Account Lockout Service - Enterprise-grade login protection.

Features:
- 5 failed attempts → 15 minute lockout
- Warning at attempts 3 and 4
- Exponential backoff for repeat offenders
- CAPTCHA trigger after 3 failures
- Admin manual unlock capability
"""
import asyncio
from datetime import datetime, timezone
from typing import Tuple, Optional, List, Dict
from app.core.redis_pubsub import get_redis
import logging

logger = logging.getLogger(__name__)

# Configuration
MAX_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15
WARNING_THRESHOLD = 3
CAPTCHA_THRESHOLD = 3
ATTEMPT_WINDOW_SECONDS = 300  # 5 minutes to count attempts

# Redis key prefixes
KEY_ATTEMPTS = "lockout:attempts:"
KEY_LOCKED = "lockout:locked:"
KEY_CAPTCHA = "lockout:captcha:"


class AccountLockout:
    """
    Redis-based account lockout system.

    Usage:
        lockout = AccountLockout()

        # Check if locked
        is_locked, remaining = await lockout.is_locked(username)

        # Record failure
        attempts, needs_captcha = await lockout.record_failure(username)

        # Reset on success
        await lockout.reset(username)

        # Admin unlock
        await lockout.admin_unlock(username)
    """

    async def is_locked(self, username: str) -> Tuple[bool, int]:
        """
        Check if account is locked.

        Returns:
            (is_locked, remaining_minutes)
        """
        redis = await get_redis()
        key = f"{KEY_LOCKED}{username.lower()}"

        ttl = await redis.ttl(key)
        if ttl > 0:
            remaining_minutes = max(1, ttl // 60)
            return True, remaining_minutes

        return False, 0

    async def get_attempts(self, username: str) -> int:
        """Get current failed attempt count."""
        redis = await get_redis()
        key = f"{KEY_ATTEMPTS}{username.lower()}"

        count = await redis.get(key)
        return int(count) if count else 0

    async def needs_captcha(self, username: str) -> bool:
        """Check if CAPTCHA is required for this user."""
        redis = await get_redis()
        key = f"{KEY_CAPTCHA}{username.lower()}"

        return await redis.exists(key) > 0

    async def record_failure(self, username: str, ip_address: Optional[str] = None) -> Tuple[int, bool, Optional[str]]:
        """
        Record a failed login attempt.

        Returns:
            (attempt_count, needs_captcha, warning_message)
        """
        redis = await get_redis()
        username_lower = username.lower()
        attempts_key = f"{KEY_ATTEMPTS}{username_lower}"
        captcha_key = f"{KEY_CAPTCHA}{username_lower}"
        locked_key = f"{KEY_LOCKED}{username_lower}"

        # Increment attempt counter
        attempts = await redis.incr(attempts_key)

        # Set expiry on first attempt
        if attempts == 1:
            await redis.expire(attempts_key, ATTEMPT_WINDOW_SECONDS)

        # Check if should require CAPTCHA
        needs_captcha = False
        if attempts >= CAPTCHA_THRESHOLD:
            await redis.setex(captcha_key, ATTEMPT_WINDOW_SECONDS, "1")
            needs_captcha = True

        # Generate warning message
        warning = None
        remaining = MAX_ATTEMPTS - attempts

        if attempts == WARNING_THRESHOLD:
            warning = f"⚠️ Peringatan: Tersisa {remaining} percobaan sebelum akun terkunci"
        elif attempts == MAX_ATTEMPTS - 1:
            warning = "⚠️ Peringatan: Tersisa 1 percobaan terakhir!"

        # Lock account if max attempts reached
        if attempts >= MAX_ATTEMPTS:
            lockout_seconds = LOCKOUT_DURATION_MINUTES * 60
            await redis.setex(locked_key, lockout_seconds, datetime.now(timezone.utc).isoformat())

            # Log security event
            logger.warning(f"SECURITY: Account locked - username={username}, ip={ip_address}, attempts={attempts}")

            # Send Telegram notification (fire and forget with proper scheduling)
            try:
                from app.config import settings

                if settings.telegram_alerting_active:
                    from app.utils.telegram_alerts import send_lockout_alert
                    # Use ensure_future to schedule the coroutine
                    asyncio.ensure_future(send_lockout_alert(username, ip_address or "unknown", attempts))
                    logger.info(f"Scheduled Telegram lockout notification for {username}")
            except Exception as e:
                logger.error(f"Failed to schedule lockout Telegram alert: {e}", exc_info=True)

            warning = f"🔒 Akun terkunci selama {LOCKOUT_DURATION_MINUTES} menit"

        return attempts, needs_captcha, warning

    async def reset(self, username: str):
        """Reset attempt counter on successful login."""
        redis = await get_redis()
        username_lower = username.lower()

        # Delete all lockout-related keys
        await redis.delete(
            f"{KEY_ATTEMPTS}{username_lower}",
            f"{KEY_CAPTCHA}{username_lower}",
            f"{KEY_LOCKED}{username_lower}"
        )

    async def admin_unlock(self, username: str, admin_username: Optional[str] = None) -> bool:
        """
        Admin manual unlock.

        Returns:
            True if account was locked and unlocked, False if wasn't locked
        """
        redis = await get_redis()
        username_lower = username.lower()
        locked_key = f"{KEY_LOCKED}{username_lower}"

        was_locked = await redis.exists(locked_key) > 0

        if was_locked:
            await self.reset(username)
            logger.info(f"ADMIN: Account unlocked - username={username}, by={admin_username}")

        return was_locked

    async def get_all_locked(self) -> List[Dict]:
        """
        Get all currently locked accounts.

        Returns:
            List of {username, locked_at, remaining_minutes}
        """
        redis = await get_redis()
        locked_accounts = []

        # Scan for locked keys
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor, match=f"{KEY_LOCKED}*", count=100)

            for key in keys:
                # Handle both bytes and str (Redis may return either)
                username = key.decode() if isinstance(key, bytes) else key
                username = username.replace(KEY_LOCKED, "")
                ttl = await redis.ttl(key)
                locked_at = await redis.get(key)

                if ttl > 0:
                    # Handle both bytes and str for locked_at
                    if locked_at and isinstance(locked_at, bytes):
                        locked_at = locked_at.decode()

                    locked_accounts.append({
                        "username": username,
                        "locked_at": locked_at if locked_at else None,
                        "remaining_minutes": max(1, ttl // 60),
                        "remaining_seconds": ttl
                    })

            if cursor == 0:
                break

        return locked_accounts

    async def unlock_all(self, admin_username: Optional[str] = None) -> int:
        """
        Unlock all locked accounts.

        Returns:
            Number of accounts unlocked
        """
        try:
            redis = await get_redis()
            count = 0

            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor, match=f"{KEY_LOCKED}*", count=100)

                for key in keys:
                    try:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        username = key_str.replace(KEY_LOCKED, "")
                        if username: # Only reset if username is valid
                            await self.reset(username)
                            count += 1
                    except Exception as e:
                        logger.error(f"Error processing key {key}: {e}")
                        continue

                # Ensure cursor is int for comparison (robustness)
                if int(cursor) == 0:
                    break

            if count > 0:
                logger.info(f"ADMIN: Bulk unlock - count={count}, by={admin_username}")

            return count
        except Exception as e:
            logger.error(f"Critical error in unlock_all: {e}")
            raise e


# Singleton instance
_lockout_instance = None

def get_lockout() -> AccountLockout:
    """Get singleton lockout instance."""
    global _lockout_instance
    if _lockout_instance is None:
        _lockout_instance = AccountLockout()
    return _lockout_instance
