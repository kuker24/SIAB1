"""
Audit Logging Service - Tracks important admin/system actions.

All sensitive operations are logged for security and compliance:
- User management (create, update, delete, role changes)
- Exam management (create, publish, delete)
- System settings changes
- Security events (password reset, 2FA changes)
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.activity_log import UserActivityLog

logger = logging.getLogger(__name__)


class AuditEventType:
    """Standard audit event types."""
    # User events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_ROLE_CHANGED = "user_role_changed"
    USER_PASSWORD_RESET = "user_password_reset"
    USER_ACTIVATED = "user_activated"
    USER_DEACTIVATED = "user_deactivated"

    # Exam events
    EXAM_CREATED = "exam_created"
    EXAM_UPDATED = "exam_updated"
    EXAM_PUBLISHED = "exam_published"
    EXAM_UNPUBLISHED = "exam_unpublished"
    EXAM_DELETED = "exam_deleted"
    EXAM_RESULTS_DELETED = "exam_results_deleted"
    EXAM_SCORES_RECALCULATED = "exam_scores_recalculated"

    # System events
    SETTINGS_CHANGED = "settings_changed"
    MAINTENANCE_ENABLED = "maintenance_enabled"
    MAINTENANCE_DISABLED = "maintenance_disabled"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"

    # Security events
    LOGIN_FAILED_BRUTE_FORCE = "login_failed_brute_force"
    SESSION_TERMINATED = "session_terminated"
    ALL_SESSIONS_REVOKED = "all_sessions_revoked"


class AuditLogger:
    """Audit logging service for tracking admin actions."""

    @staticmethod
    async def log(
        db: AsyncSession,
        user_id: int,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
        target_user_id: Optional[int] = None,
        target_exam_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> UserActivityLog:
        """
        Log an audit event.

        Args:
            db: Database session
            user_id: ID of user performing the action
            event_type: Type of event (use AuditEventType constants)
            event_data: Additional event details
            target_user_id: ID of target user (if applicable)
            target_exam_id: ID of target exam (if applicable)
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Created activity log entry
        """
        # Build event data with context
        full_event_data = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip_address": ip_address,
            "user_agent": user_agent[:500] if user_agent else None,
            **(event_data or {})
        }

        if target_user_id:
            full_event_data["target_user_id"] = target_user_id
        if target_exam_id:
            full_event_data["target_exam_id"] = target_exam_id

        # Create log entry
        log_entry = UserActivityLog(
            user_id=user_id,
            event_type=event_type,
            event_data=full_event_data
        )

        db.add(log_entry)
        await db.commit()
        await db.refresh(log_entry)

        # Also log to application logger for monitoring
        logger.info(
            f"AUDIT: user={user_id} action={event_type} "
            f"target_user={target_user_id} target_exam={target_exam_id} "
            f"ip={ip_address}"
        )

        return log_entry

    @staticmethod
    async def log_user_action(
        db: AsyncSession,
        admin_user_id: int,
        event_type: str,
        target_user_id: int,
        changes: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> UserActivityLog:
        """Log an action on a user (convenient wrapper)."""
        return await AuditLogger.log(
            db=db,
            user_id=admin_user_id,
            event_type=event_type,
            event_data={"changes": changes} if changes else None,
            target_user_id=target_user_id,
            ip_address=ip_address
        )

    @staticmethod
    async def log_exam_action(
        db: AsyncSession,
        user_id: int,
        event_type: str,
        exam_id: int,
        exam_title: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> UserActivityLog:
        """Log an action on an exam (convenient wrapper)."""
        event_data = details or {}
        if exam_title:
            event_data["exam_title"] = exam_title

        return await AuditLogger.log(
            db=db,
            user_id=user_id,
            event_type=event_type,
            event_data=event_data,
            target_exam_id=exam_id,
            ip_address=ip_address
        )

    @staticmethod
    async def log_settings_change(
        db: AsyncSession,
        user_id: int,
        setting_name: str,
        old_value: Any,
        new_value: Any,
        ip_address: Optional[str] = None
    ) -> UserActivityLog:
        """Log a system settings change."""
        return await AuditLogger.log(
            db=db,
            user_id=user_id,
            event_type=AuditEventType.SETTINGS_CHANGED,
            event_data={
                "setting": setting_name,
                "old_value": str(old_value)[:200],  # Limit size
                "new_value": str(new_value)[:200]
            },
            ip_address=ip_address
        )


# Convenience function for one-liner logging
async def audit_log(
    db: AsyncSession,
    user_id: int,
    event_type: str,
    **kwargs
) -> UserActivityLog:
    """Quick audit log function."""
    return await AuditLogger.log(db, user_id, event_type, **kwargs)
