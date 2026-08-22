"""
System Settings API
Manage system-wide configuration
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List

from app.database import get_db
from app.core.security import (
    get_current_active_admin,
    get_current_user,
    is_freeze_exempt_identity,
)
from app.models.user import User
from app.config import settings as app_settings
from app.models.system_settings import SystemSettings
from app.core.cache import clear_developer_mode_cache
from app.core.apk_profiles import (
    clean_token,
    encode_signature_profiles,
    encode_token_profiles,
    parse_signature_profiles,
    parse_token_profiles,
)
from app.utils.telegram_utils import send_maintenance_start_notification, send_maintenance_end_notification
from datetime import datetime
import logging
import asyncio
import re

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _mask_token(token: Optional[str]) -> str:
    value = (token or "").strip()
    if not value:
        return "not-set"
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


class SystemSettingsUpdate(BaseModel):
    allow_browser_testing: Optional[bool] = None
    allow_mobile_apps: Optional[bool] = None
    maintenance_mode: Optional[bool] = None
    freeze_mode: Optional[bool] = None
    minimum_apk_token: Optional[str] = None
    allowed_signatures: Optional[str] = None
    stable_apk_token: Optional[str] = None
    stable_apk_enabled: Optional[bool] = None
    new_update_apk_token: Optional[str] = None
    stable_signatures: Optional[List[str]] = None
    new_update_signatures: Optional[List[str]] = None
    token_validation_bypass: Optional[bool] = None
    app_name: Optional[str] = None
    timezone: Optional[str] = None


@router.get("/timezone")
async def get_timezone(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get system timezone (accessible to all authenticated users)
    """
    result = await db.execute(select(SystemSettings))
    settings = result.scalar_one_or_none()

    if not settings:
        # Return default timezone
        return {"timezone": "Asia/Jakarta"}

    return {"timezone": settings.timezone or "Asia/Jakarta"}


@router.get("/system")
async def get_system_settings(
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get current system settings (admin only)
    """
    result = await db.execute(select(SystemSettings))
    settings = result.scalar_one_or_none()

    if not settings:
        # Create default settings if not exists
        settings = SystemSettings(
            allow_browser_testing=False,
            allow_mobile_apps=True,
            maintenance_mode=False,
            freeze_mode=False
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return settings.to_dict()


@router.put("/system")
async def update_system_settings(
    update: SystemSettingsUpdate,
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update system settings (admin only)
    """
    result = await db.execute(select(SystemSettings))
    settings = result.scalar_one_or_none()

    if not settings:
        settings = SystemSettings()
        db.add(settings)

    # Update fields
    old_dev_mode = settings.allow_browser_testing
    old_maintenance = settings.maintenance_mode
    old_freeze = bool(getattr(settings, "freeze_mode", False))

    if update.allow_browser_testing is not None:
        settings.allow_browser_testing = update.allow_browser_testing

    if update.allow_mobile_apps is not None:
        settings.allow_mobile_apps = update.allow_mobile_apps

    if update.maintenance_mode is not None:
        settings.maintenance_mode = update.maintenance_mode

    if update.freeze_mode is not None:
        if update.freeze_mode and not is_freeze_exempt_identity(
            current_user.role,
            current_user.username,
            current_user.job_title,
        ):
            raise HTTPException(
                status_code=403,
                detail="Freeze mode hanya bisa diaktifkan oleh akun developer-exempt.",
            )
        settings.freeze_mode = update.freeze_mode

    if update.app_name is not None:
        settings.app_name = update.app_name

    if update.timezone is not None:
        settings.timezone = update.timezone

    if update.minimum_apk_token is not None:
        # Validate APK token format if not empty
        token = update.minimum_apk_token.strip() if update.minimum_apk_token else ""

        if token:  # Only validate if not empty (empty means allow all APKs)
            # Token format: BUILD-YYYYMMDDHHMMSS-XXXXXX
            token_pattern = r'^BUILD-\d{14}-[A-Z0-9]{6}$'
            if not re.match(token_pattern, token):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "INVALID_TOKEN_FORMAT",
                        "message": "Format token APK tidak valid. Silakan copy dari APK Builder GUI."
                    }
                )

        old_token = settings.minimum_apk_token
        settings.minimum_apk_token = token if token else None
        logger.warning(
            "Minimum APK Token changed by admin %s (ID: %s). Old: %s, New: %s",
            current_user.username,
            current_user.id,
            _mask_token(old_token),
            _mask_token(token),
        )

    if update.allowed_signatures is not None:
        sigs = update.allowed_signatures.strip()
        settings.allowed_signatures = sigs if sigs else None
        logger.info(f"Allowed App Signatures updated by admin {current_user.username}")

    dual_token_requested = (
        update.stable_apk_token is not None or update.new_update_apk_token is not None
    )
    stable_toggle_requested = update.stable_apk_enabled is not None
    dual_signature_requested = (
        update.stable_signatures is not None or update.new_update_signatures is not None
    )

    if dual_token_requested or stable_toggle_requested:
        current_profiles = parse_token_profiles(settings.minimum_apk_token)
        stable_token = current_profiles.get("stable")
        new_update_token = current_profiles.get("new_update")
        stable_enabled = bool(current_profiles.get("stable_enabled", True))

        if update.stable_apk_token is not None:
            raw_stable = update.stable_apk_token.strip() if update.stable_apk_token else ""
            if raw_stable:
                validated_stable = clean_token(raw_stable)
                if not validated_stable:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "INVALID_STABLE_TOKEN_FORMAT",
                            "message": "Format token stable tidak valid. Gunakan BUILD-YYYYMMDDHHMMSS-XXXXXX.",
                        },
                    )
                stable_token = validated_stable
            else:
                stable_token = None

        if update.new_update_apk_token is not None:
            raw_new = update.new_update_apk_token.strip() if update.new_update_apk_token else ""
            if raw_new:
                validated_new = clean_token(raw_new)
                if not validated_new:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "INVALID_NEW_UPDATE_TOKEN_FORMAT",
                            "message": "Format token new update tidak valid. Gunakan BUILD-YYYYMMDDHHMMSS-XXXXXX.",
                        },
                    )
                new_update_token = validated_new
            else:
                new_update_token = None

        if update.stable_apk_enabled is not None:
            stable_enabled = bool(update.stable_apk_enabled)

        settings.minimum_apk_token = encode_token_profiles(
            stable_token,
            new_update_token,
            stable_enabled=stable_enabled,
        )
        logger.warning(
            "APK token profiles updated by admin %s stable=%s stable_enabled=%s new_update=%s",
            current_user.username,
            bool(stable_token),
            stable_enabled,
            bool(new_update_token),
        )

    if dual_signature_requested:
        current_sig_profiles = parse_signature_profiles(settings.allowed_signatures)
        stable_signatures = current_sig_profiles.get("stable", [])
        new_update_signatures = current_sig_profiles.get("new_update", [])

        if update.stable_signatures is not None:
            stable_signatures = update.stable_signatures
        if update.new_update_signatures is not None:
            new_update_signatures = update.new_update_signatures

        settings.allowed_signatures = encode_signature_profiles(
            stable_signatures,
            new_update_signatures,
        )
        logger.info(
            "APK signature profiles updated by admin %s stable_count=%s new_update_count=%s",
            current_user.username,
            len(stable_signatures),
            len(new_update_signatures),
        )

    # Emergency bypass toggle
    old_bypass = settings.token_validation_bypass if hasattr(settings, 'token_validation_bypass') else False
    if update.token_validation_bypass is not None:
        settings.token_validation_bypass = update.token_validation_bypass
        logger.warning(
            f"APK Token Validation Bypass {'ENABLED' if update.token_validation_bypass else 'DISABLED'} "
            f"by admin {current_user.username} (ID: {current_user.id}). "
            f"Previous: {old_bypass}. "
            f"{'⚠️ ALL STUDENTS CAN NOW LOGIN WITHOUT TOKEN CHECK!' if update.token_validation_bypass else '✅ Token validation re-enabled.'}"
        )

    settings.updated_by = current_user.id
    settings.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(settings)

    # Clear cache to apply changes immediately
    await clear_developer_mode_cache()

    # Log changes
    if update.allow_browser_testing is not None and old_dev_mode != update.allow_browser_testing:
        logger.warning(
            f"Developer Mode {'ENABLED' if update.allow_browser_testing else 'DISABLED'} "
            f"by admin user {current_user.username} (ID: {current_user.id}). "
            f"Previous value: {old_dev_mode}"
        )

    if update.allow_mobile_apps is not None:
        logger.info(
            f"Mobile Apps Access {'ENABLED' if update.allow_mobile_apps else 'DISABLED'} "
            f"by admin user {current_user.username} (ID: {current_user.id})"
        )

    if update.maintenance_mode is not None and old_maintenance != update.maintenance_mode:
        logger.warning(
            f"Maintenance Mode {'ENABLED' if update.maintenance_mode else 'DISABLED'} "
            f"by admin user {current_user.username} (ID: {current_user.id}). "
            f"Previous value: {old_maintenance}. "
            f"{'NON-ADMIN ACCESS BLOCKED' if update.maintenance_mode else 'NORMAL OPERATION RESUMED'}"
        )

        # Send Telegram notification asynchronously (fire and forget)
        if app_settings.telegram_alerting_active:
            async def send_notification():
                try:
                    if update.maintenance_mode:
                        # Maintenance mode activated
                        await send_maintenance_start_notification(current_user.username)
                    else:
                        # Maintenance mode deactivated
                        await send_maintenance_end_notification(current_user.username)
                except Exception:
                    logger.exception("Failed to send Telegram notification for maintenance mode")

            # Create task to send notification without blocking response
            asyncio.create_task(send_notification())

    if update.freeze_mode is not None and old_freeze != update.freeze_mode:
        logger.critical(
            "Freeze Mode %s by admin user %s (ID: %s). Previous value: %s. "
            "All non-developer actions are now %s.",
            "ENABLED" if update.freeze_mode else "DISABLED",
            current_user.username,
            current_user.id,
            old_freeze,
            "LOCKED" if update.freeze_mode else "RESUMED",
        )

    return {
        "success": True,
        "message": "Settings updated successfully",
        "settings": settings.to_dict()
    }
