"""
APK Token Validation Utility
============================
Validates APK build tokens to ensure students use approved app versions.

Token Format: BUILD-YYYYMMDDHHMMSS-XXXXXX
Example: BUILD-20260125120000-ABC123

Validation Logic:
- String comparison (lexicographic ordering matches chronological ordering)
- Newer tokens (higher timestamp) are accepted
- Older tokens (lower timestamp) are rejected
- Empty client token = Browser login attempt (rejected for students)
- Empty server token = Development mode (bypass validation)
"""

import asyncio
import logging
import re
import time
from typing import Dict, Optional
from sqlalchemy import select
from app.database import async_session_read
from app.core.apk_profiles import get_token_label, parse_token_profiles
from app.core.roles import MONITOR_SCOPE_ROLES, PARTICIPANT_ROLES
from app.core.start_db_admission import start_db_segment
from app.models.system_settings import SystemSettings

logger = logging.getLogger(__name__)

_SETTINGS_CACHE_TTL_SECONDS = 300
_settings_cache = {
    "expires_at": 0.0,
    "minimum_token": None,
    "allowed_tokens": [],
    "token_profiles": {"stable": None, "new_update": None, "tokens": [], "labels_by_token": {}},
    "token_validation_bypass": False,
    "settings_fetch_error": False,
}
_settings_cache_lock = asyncio.Lock()


def _mask_token(token: Optional[str]) -> str:
    value = str(token or "").strip()
    if not value:
        return "not-set"
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


async def _get_settings_cache() -> Dict[str, Optional[str]]:
    """Get APK-related system settings with short in-memory cache."""
    now = time.monotonic()
    if now < _settings_cache["expires_at"]:
        return _settings_cache

    async with _settings_cache_lock:
        now = time.monotonic()
        if now < _settings_cache["expires_at"]:
            return _settings_cache

        minimum_token = None
        allowed_tokens = []
        token_profiles = {"stable": None, "new_update": None, "tokens": [], "labels_by_token": {}}
        token_validation_bypass = False
        settings_fetch_error = False
        try:
            async with start_db_segment("security"):
                async with async_session_read() as db:
                    settings = await db.execute(select(SystemSettings))
                    result = settings.scalar_one_or_none()
                    if result:
                        minimum_token = result.minimum_apk_token
                        token_profiles = parse_token_profiles(result.minimum_apk_token)
                        allowed_tokens = token_profiles.get("tokens", [])
                        token_validation_bypass = bool(result.token_validation_bypass)
        except Exception:
            settings_fetch_error = True
            minimum_token = _settings_cache["minimum_token"]
            allowed_tokens = _settings_cache.get("allowed_tokens", [])
            token_profiles = _settings_cache.get("token_profiles", token_profiles)
            token_validation_bypass = bool(_settings_cache["token_validation_bypass"])

        _settings_cache["minimum_token"] = minimum_token
        _settings_cache["allowed_tokens"] = allowed_tokens
        _settings_cache["token_profiles"] = token_profiles
        _settings_cache["token_validation_bypass"] = token_validation_bypass
        _settings_cache["settings_fetch_error"] = settings_fetch_error
        _settings_cache["expires_at"] = now + (2 if settings_fetch_error else _SETTINGS_CACHE_TTL_SECONDS)
        return _settings_cache


class APKTokenValidator:
    """APK token validation with security logging"""

    TOKEN_PATTERN = r'^BUILD-\d{14}-[A-Z0-9]{6}$'

    @staticmethod
    def validate_token_format(token: str) -> bool:
        """
        Validate token format matches BUILD-YYYYMMDDHHMMSS-XXXXXX

        Args:
            token: Token string to validate

        Returns:
            True if format is valid, False otherwise
        """
        if not token:
            return False
        return bool(re.match(APKTokenValidator.TOKEN_PATTERN, token))

    @staticmethod
    async def get_minimum_token() -> Optional[str]:
        """
        Get stable/legacy token from database.

        Returns:
            Stable token string or None if not set
        """
        cached = await _get_settings_cache()
        profiles = cached.get("token_profiles", {})
        stable = profiles.get("stable") if isinstance(profiles, dict) else None
        if stable:
            return stable
        allowed_tokens = cached.get("allowed_tokens", [])
        if isinstance(allowed_tokens, list) and allowed_tokens:
            return allowed_tokens[0]
        return None

    @staticmethod
    async def get_allowed_tokens() -> list[str]:
        """Get all allowed tokens (stable + new update)."""
        cached = await _get_settings_cache()
        allowed_tokens = cached.get("allowed_tokens")
        return allowed_tokens if isinstance(allowed_tokens, list) else []

    @staticmethod
    async def is_bypass_enabled() -> bool:
        """
        Check if emergency bypass is enabled

        Returns:
            True if bypass is active, False otherwise
        """
        cached = await _get_settings_cache()
        return bool(cached.get("token_validation_bypass"))

    @staticmethod
    def compare_tokens(client_token: str, required_token: str) -> bool:
        """
        Compare tokens using EXACT MATCH

        Tokens use format BUILD-YYYYMMDDHHMMSS-XXXXXX where:
        - YYYY = year
        - MM = month
        - DD = day
        - HH = hour
        - MM = minute
        - SS = second
        - XXXXXX = random suffix

        STRICT MODE: Only the EXACT version set in settings is allowed.
        Older versions AND newer versions are BLOCKED.

        Args:
            client_token: Token from mobile client
            required_token: Required token from server (exact match)

        Returns:
            True if client_token == required_token (EXACT MATCH), False otherwise
        """
        # EXACT MATCH - Only the specific version set in settings is allowed
        is_valid = client_token == required_token

        logger.debug(
            "Token comparison (EXACT): client=%s required=%s result=%s",
            _mask_token(client_token),
            _mask_token(required_token),
            is_valid,
        )

        return is_valid

    @staticmethod
    def compare_with_allowed_tokens(client_token: str, allowed_tokens: list[str]) -> bool:
        """Validate token against multiple accepted versions."""
        normalized_client = str(client_token or "").strip().upper()
        if not normalized_client:
            return False
        normalized_allowed = [str(token or "").strip().upper() for token in allowed_tokens or []]
        return normalized_client in normalized_allowed

    @staticmethod
    async def validate_apk_token(
        client_token: Optional[str],
        user_role: str,
        username: str = "unknown",
        user_agent: str = ""
    ) -> Dict[str, any]:
        """
        Main validation function with role-based logic

        Args:
            client_token: Token sent by client (None for web login)
            user_role: User role (developer, admin, teacher, gurupengawas, student, guruplus)
            username: Username for logging
            user_agent: User Agent string for SEB/Exambro detection

        Returns:
            Dict with validation result
        """
        logger.debug(
            "APK token validation user=%s role=%s client_token=%s ua=%s",
            username,
            user_role,
            _mask_token(client_token),
            user_agent,
        )

        # Check emergency bypass first
        bypass_enabled = await APKTokenValidator.is_bypass_enabled()
        if bypass_enabled:
            logger.info("APK token bypass active for user=%s", username)
            return {
                "valid": True,
                "bypass_active": True,
                "reason": "Emergency bypass active"
            }

        # Check Developer Mode - if enabled, allow all browser access
        from app.core.cache import is_developer_mode_enabled
        developer_mode = await is_developer_mode_enabled()
        if developer_mode:
            logger.info("Developer mode active, bypassing APK token check for user=%s", username)
            return {
                "valid": True,
                "bypass_active": False,
                "reason": "Developer mode active (allow_browser_testing=True)"
            }

        # Control-plane staff can login from web without an APK token.
        if user_role in MONITOR_SCOPE_ROLES:
            logger.debug(f"Role-based bypass for {user_role} user={username}")
            return {
                "valid": True,
                "bypass_active": False,
                "reason": "Role-based bypass (control-plane staff)"
            }

        # Student/GuruPlus participants MUST use mobile app with valid token
        if user_role in PARTICIPANT_ROLES:
            # Get minimum required token and fetch state from short-lived cache
            settings_cached = await _get_settings_cache()
            minimum_token = settings_cached.get("minimum_token")
            allowed_tokens = settings_cached.get("allowed_tokens") or []
            settings_fetch_error = bool(settings_cached.get("settings_fetch_error"))

            logger.debug(
                "Participant token check user=%s role=%s client=%s allowed_tokens=%s",
                username,
                user_role,
                _mask_token(client_token),
                [_mask_token(token) for token in allowed_tokens],
            )

            if settings_fetch_error and not allowed_tokens:
                logger.warning(
                    "APK settings unavailable with empty cache for user=%s; rejecting login",
                    username,
                )
                return {
                    "valid": False,
                    "bypass_active": False,
                    "reason": "APK_VALIDATION_UNAVAILABLE",
                    "message": "Validasi aplikasi sedang tidak tersedia. Coba lagi beberapa saat.",
                    "action_required": "Jika masalah berlanjut, hubungi admin.",
                }

            # STRICT MODE: No minimum token set = Block APK access
            # Admin MUST configure minimum_apk_token for APK to work
            if not allowed_tokens:
                logger.warning(f"STRICT MODE: No minimum token configured - blocking APK user={username}")
                return {
                    "valid": False,
                    "bypass_active": False,
                    "reason": "APK_NOT_CONFIGURED",
                    "message": "Sistem APK belum dikonfigurasi oleh admin.",
                    "action_required": "Hubungi admin untuk mengatur APK Token di Pengaturan Sistem."
                }

            # Browser login attempt (no token provided)
            # SECURITY: User-Agent alone is spoofable, so we never bypass on UA.
            if not client_token:
                logger.warning(f"APK_TOKEN_MISSING for student user={username}")
                return {
                    "valid": False,
                    "bypass_active": False,
                    "reason": "APK_TOKEN_MISSING",
                    "message": "Aplikasi mobile diperlukan untuk ujian. Silakan gunakan aplikasi resmi.",
                    "action_required": "Hubungi guru atau admin untuk mendapatkan aplikasi ujian.",
                }

            # Validate token format
            if not APKTokenValidator.validate_token_format(client_token):
                logger.warning(
                    "APK_TOKEN_INVALID_FORMAT for user=%s token=%s",
                    username,
                    _mask_token(client_token),
                )
                return {
                    "valid": False,
                    "bypass_active": False,
                    "reason": "APK_TOKEN_INVALID_FORMAT",
                    "message": "Token aplikasi tidak valid.",
                    "action_required": "Silakan install ulang aplikasi dari sumber resmi.",
                }

            # Compare tokens (allow stable + new update profiles)
            if not APKTokenValidator.compare_with_allowed_tokens(client_token, allowed_tokens):
                logger.warning(
                    "APK_VERSION_MISMATCH for user=%s client=%s allowed=%s",
                    username,
                    _mask_token(client_token),
                    [_mask_token(token) for token in allowed_tokens],
                )
                return {
                    "valid": False,
                    "bypass_active": False,
                    "reason": "APK_VERSION_MISMATCH",
                    "message": "Versi aplikasi Anda tidak sesuai dengan yang diizinkan.",
                    "action_required": "Silakan hubungi guru atau admin untuk mendapatkan aplikasi versi yang benar.",
                }

            # Valid token
            logger.debug("Token valid for user=%s", username)
            accepted_label = get_token_label(minimum_token, client_token)
            return {
                "valid": True,
                "bypass_active": False,
                "reason": "Valid token",
                "accepted_label": accepted_label,
            }

        # Unknown role - reject for safety
        logger.error(f"UNKNOWN_ROLE for user={username}: role={user_role}")
        return {
            "valid": False,
            "bypass_active": False,
            "reason": "UNKNOWN_ROLE",
            "message": "Role pengguna tidak valid."
        }


async def validate_student_apk_token(
    client_token: Optional[str],
    user_role: str,
    username: str = "unknown",
    user_agent: str = ""
) -> Dict[str, any]:
    """
    Convenience function for APK token validation

    Args:
        client_token: Token from client
        user_role: User role
        username: Username for logging
        user_agent: User Agent string

    Returns:
        Validation result dict
    """
    return await APKTokenValidator.validate_apk_token(client_token, user_role, username, user_agent)
