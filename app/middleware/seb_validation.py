"""
SEB Validation Middleware for enforcing Safe Exam Browser access.

ENHANCED VERSION (v2.0):
- Challenge-response anti-spoofing validation
- Enhanced security event logging
- Configurable via settings.seb_challenge_enabled
- Mobile app bypass via X-Build-Token
"""
import asyncio
import time
from typing import Optional, Tuple

from fastapi import Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.seb import (
    validate_seb_config_key_hash,
    validate_seb_request_hash,
    validate_seb_challenge_response,
    generate_seb_challenge
)
from app.models.exam import Exam
from app.models.system_settings import SystemSettings
from app.config import settings

_ALLOW_MOBILE_CACHE_TTL_SECONDS = 300
_allow_mobile_cache = {
    "expires_at": 0.0,
    "allow_mobile": True,
}
_allow_mobile_cache_lock = asyncio.Lock()

_EXAM_SEB_KEYS_CACHE_TTL_SECONDS = 15
_exam_seb_keys_cache: dict[int, tuple[float, str, Optional[str]]] = {}
_exam_seb_keys_cache_lock = asyncio.Lock()


async def _get_allow_mobile_apps_cached() -> bool:
    """Get allow_mobile_apps flag with short in-memory cache."""
    now = time.monotonic()
    if now < _allow_mobile_cache["expires_at"]:
        return bool(_allow_mobile_cache["allow_mobile"])

    async with _allow_mobile_cache_lock:
        now = time.monotonic()
        if now < _allow_mobile_cache["expires_at"]:
            return bool(_allow_mobile_cache["allow_mobile"])

        try:
            from app.database import async_session_read
            async with async_session_read() as session:
                result = await session.execute(select(SystemSettings.allow_mobile_apps))
                allow_mobile = result.scalar_one_or_none()
            _allow_mobile_cache["allow_mobile"] = True if allow_mobile is None else bool(allow_mobile)
        except Exception:
            # Keep the last known value during transient DB pressure.
            allow_mobile = _allow_mobile_cache["allow_mobile"]
        _allow_mobile_cache["expires_at"] = now + _ALLOW_MOBILE_CACHE_TTL_SECONDS
        return bool(_allow_mobile_cache["allow_mobile"])


async def _get_exam_seb_keys_cached(
    db: AsyncSession,
    exam_id: int,
) -> Optional[Tuple[str, Optional[str]]]:
    """
    Resolve exam SEB keys with a short local cache.

    This avoids an extra DB lookup on every submit-answer/start/submit call
    during burst traffic while keeping key rotation impact minimal.
    """
    now = time.monotonic()
    cached = _exam_seb_keys_cache.get(exam_id)
    if cached and now < cached[0]:
        return cached[1], cached[2]

    async with _exam_seb_keys_cache_lock:
        now = time.monotonic()
        cached = _exam_seb_keys_cache.get(exam_id)
        if cached and now < cached[0]:
            return cached[1], cached[2]

        result = await db.execute(
            select(Exam.seb_config_key, Exam.seb_browser_exam_key).where(Exam.id == exam_id)
        )
        row = result.first()
        if not row:
            return None

        seb_config_key = str(row[0] or "")
        seb_browser_exam_key = row[1]
        _exam_seb_keys_cache[exam_id] = (
            now + _EXAM_SEB_KEYS_CACHE_TTL_SECONDS,
            seb_config_key,
            seb_browser_exam_key,
        )

        # Keep cache bounded in long-lived workers.
        if len(_exam_seb_keys_cache) > 4096:
            expired_ids = [
                key for key, (expires_at, _cfg, _browser) in _exam_seb_keys_cache.items()
                if expires_at <= now
            ]
            for key in expired_ids[:2048]:
                _exam_seb_keys_cache.pop(key, None)

        return seb_config_key, seb_browser_exam_key


class SEBValidationError(HTTPException):
    """Custom exception for SEB validation failures."""

    def __init__(self, exam_id: int, detail: str, error_code: str):
        super().__init__(
            status_code=403,
            detail={
                "error": error_code,
                "message": detail,
                "download_config": f"/api/exams/{exam_id}/seb-config.seb",
                "mobile_launch_ios": f"/api/exams/{exam_id}/seb-launch-mobile?platform=ios",
                "mobile_launch_android": f"/api/exams/{exam_id}/seb-launch-mobile?platform=android"
            }
        )


async def validate_seb_headers(
    request: Request,
    exam_id: int,
    db: AsyncSession,
    require_seb: bool = True
) -> bool:
    """
    Validate SEB headers for exam access with challenge-response.

    ENHANCED VALIDATION FLOW:
    0. [NEW] Check if developer/tester mode is enabled - bypass if true
    0.5 [NEW] Check if mobile app with valid build token - bypass if true
    1. Check if SEB headers are present (X-SafeExamBrowser-ConfigKeyHash)
    2. Validate Config Key Hash against exam's seb_config_key
    3. Validate Request Hash (if browser exam key is set)
    4. [NEW] Validate Challenge-Response (if enabled)

    Args:
        request: FastAPI request object
        exam_id: Exam ID being accessed
        db: Database session
        require_seb: Whether to require SEB (can be disabled for admin access)

    Returns:
        True if SEB validation passes or is not required

    Raises:
        SEBValidationError: If SEB validation fails
    """
    # DEVELOPER MODE CHECK: Allow browser access if enabled
    from app.core.cache import is_developer_mode_enabled
    if await is_developer_mode_enabled():
        # Log this bypass for security monitoring
        await _log_security_event(
            request, exam_id, "DEVELOPER_MODE_BYPASS",
            "SEB validation bypassed due to developer/tester mode being enabled"
        )
        return True

    # MOBILE APP CHECK: Allow official mobile app access based on build token
    # This is now INDEPENDENT from developer mode for production safety
    build_token = request.headers.get("X-Build-Token")
    user_agent = request.headers.get("user-agent", "").lower()

    # Check if this is a mobile APK (SXB-Client or Exambro)
    is_mobile_apk = "sxb-client" in user_agent or "exambro" in user_agent

    if build_token or is_mobile_apk:
        # Check if mobile apps are allowed (separate setting)
        from app.core.cache import get_allowed_signatures
        allow_mobile = await _get_allow_mobile_apps_cached()

        if allow_mobile:
            # Allow if:
            # 1) Build token format is valid, OR
            # 2) Signature header matches admin-configured signature and timestamp is fresh.
            token_valid = False
            if build_token:
                from app.utils.apk_validation import APKTokenValidator
                if APKTokenValidator.validate_token_format(build_token):
                    allowed_tokens = await APKTokenValidator.get_allowed_tokens()
                    token_valid = APKTokenValidator.compare_with_allowed_tokens(
                        build_token,
                        allowed_tokens,
                    )

            signature_valid = False
            app_sig = request.headers.get("X-App-Signature")
            app_ts = request.headers.get("X-App-Timestamp")
            if app_sig:
                allowed_sigs = await get_allowed_signatures()
                normalized_sig = app_sig.replace(":", "").lower().strip()
                signature_valid = any(
                    s and s.strip().lower() == normalized_sig for s in allowed_sigs
                )
                if signature_valid:
                    try:
                        if not app_ts:
                            signature_valid = False
                        else:
                            now_ts = int(time.time())
                            client_ts = int(app_ts)
                            signature_valid = abs(now_ts - client_ts) <= 3600
                    except Exception:
                        signature_valid = False

            if token_valid or signature_valid:
                await _log_security_event(
                    request, exam_id, "MOBILE_APP_ACCESS",
                    (
                        "SEB validation bypassed for trusted mobile app "
                        f"(UA: {is_mobile_apk}, Token: {token_valid}, Signature: {signature_valid})"
                    )
                )
                return True
            elif is_mobile_apk:
                await _log_security_event(
                    request, exam_id, "MOBILE_APP_UNTRUSTED",
                    "Mobile User-Agent detected without valid build token/signature"
                )
        else:
            # Mobile apps are disabled
            await _log_security_event(
                request, exam_id, "MOBILE_APP_BLOCKED",
                "Mobile app access is currently disabled in settings"
            )

    # Get SEB headers
    config_key_hash = request.headers.get("X-SafeExamBrowser-ConfigKeyHash")
    request_hash = request.headers.get("X-SafeExamBrowser-RequestHash")

    # Challenge-response headers (new)
    challenge_token = request.headers.get("X-SEB-Challenge-Token")
    challenge_response = request.headers.get("X-SEB-Challenge-Response")

    # If SEB is not required, allow access
    if not require_seb:
        return True

    # Check if SEB headers are present
    if not config_key_hash:
        # SECURITY FIX: Removed insecure User-Agent bypass.
        # All clients (Desktop & Mobile) MUST send valid SEB headers.
        # If mobile SEB fails, use proper configuration, not UA spoofing.

        raise SEBValidationError(
            exam_id=exam_id,
            detail="Ujian ini harus diakses melalui Aplikasi Ujian (APK) atau Safe Exam Browser",
            error_code="SEB_REQUIRED"
        )

    exam_seb_keys = await _get_exam_seb_keys_cached(db, exam_id)
    if exam_seb_keys is None:
        raise HTTPException(status_code=404, detail="Ujian tidak ditemukan")
    exam_seb_config_key, exam_seb_browser_key = exam_seb_keys

    # Validate Config Key Hash
    if not validate_seb_config_key_hash(config_key_hash, exam_seb_config_key):
        # Log security event
        await _log_security_event(
            request, exam_id, "INVALID_SEB_CONFIG_KEY",
            "Config key hash mismatch - possible spoofing attempt"
        )

        raise SEBValidationError(
            exam_id=exam_id,
            detail="Konfigurasi SEB tidak valid",
            error_code="INVALID_SEB_CONFIG"
        )

    # Validate Request Hash if browser exam key is set
    if exam_seb_browser_key and request_hash:
        request_url = str(request.url)
        if not validate_seb_request_hash(request_hash, exam_seb_browser_key, request_url):
            await _log_security_event(
                request, exam_id, "INVALID_SEB_REQUEST_HASH",
                "Request hash mismatch"
            )

            raise SEBValidationError(
                exam_id=exam_id,
                detail="Verifikasi permintaan gagal",
                error_code="INVALID_REQUEST_HASH"
            )

    # ==================== CHALLENGE-RESPONSE VALIDATION (NEW) ====================
    if settings.seb_challenge_enabled:
        # If challenge headers are provided, validate them
        if challenge_token and challenge_response:
            is_valid = await validate_seb_challenge_response(
                challenge_token,
                challenge_response,
                exam_id
            )

            if not is_valid:
                await _log_security_event(
                    request, exam_id, "CHALLENGE_VALIDATION_FAILED",
                    "Challenge-response validation failed - possible replay or spoofing attack"
                )

                raise SEBValidationError(
                    exam_id=exam_id,
                    detail="Validasi challenge gagal. Kemungkinan serangan spoofing terdeteksi.",
                    error_code="CHALLENGE_FAILED"
                )

    return True


async def get_new_challenge(exam_id: int) -> dict:
    """
    Generate a new challenge for SEB client.

    Call this endpoint before critical operations that need extra security.
    Client should compute: SHA256(challenge + config_key + exam_id)
    and include result in X-SEB-Challenge-Response header.

    Args:
        exam_id: Exam ID for context

    Returns:
        dict with challenge token and expiration
    """
    return await generate_seb_challenge(exam_id)


async def _log_security_event(
    request: Request,
    exam_id: int,
    event_type: str,
    details: str
) -> None:
    """Log security event to Redis pub/sub for monitoring."""
    try:
        from app.core.redis_pubsub import publish_message

        await publish_message("security_events", {
            "event": event_type,
            "exam_id": exam_id,
            "details": details,
            "ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
            "headers": {
                "config_key_hash": request.headers.get("X-SafeExamBrowser-ConfigKeyHash", "missing"),
                "request_hash": request.headers.get("X-SafeExamBrowser-RequestHash", "missing"),
                "challenge_token": request.headers.get("X-SEB-Challenge-Token", "missing"),
                "build_token": request.headers.get("X-Build-Token", "missing"),
            }
        })
    except Exception as e:
        # Don't fail the request if logging fails, but log the error
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Security event logging failed: {e}")


def get_seb_detected(request: Request) -> bool:
    """Check if request is coming from SEB."""
    config_key_hash = request.headers.get("X-SafeExamBrowser-ConfigKeyHash")
    return config_key_hash is not None


def get_client_info(request: Request) -> dict:
    """Extract client info from request."""
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "unknown"),
        "seb_detected": get_seb_detected(request),
        "mobile_app_detected": request.headers.get("X-Build-Token") is not None,
        "challenge_enabled": settings.seb_challenge_enabled
    }
