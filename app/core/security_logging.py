"""
Security logging utilities for audit trail and monitoring.
Logs all security-relevant events for compliance and forensics.
"""
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional, Dict, Any
import json
import os


def _resolve_logs_dir() -> Optional[str]:
    """Find a writable logs directory."""
    candidates = ["logs", "/tmp/ujian_logs"]
    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
            if os.access(candidate, os.W_OK):
                return candidate
        except (PermissionError, OSError):
            continue
    return None


logs_dir = _resolve_logs_dir()


# Configure security logger
security_logger = logging.getLogger('security')
security_logger.setLevel(logging.INFO)

# Try to use file handler, fallback to console if permission denied
try:
    if logs_dir:
        # Rotating file handler (10MB per file, keep 10 backups)
        security_handler = RotatingFileHandler(
            os.path.join(logs_dir, 'security.log'),
            maxBytes=10*1024*1024,  # 10MB
            backupCount=10,
            encoding='utf-8'
        )
    else:
        raise PermissionError("Logs directory not writable")
except (PermissionError, OSError) as e:
    # Fallback to console logging
    security_handler = logging.StreamHandler()
    security_logger.warning(f"File logging disabled, using console: {e}")

# JSON formatter for structured logging
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'event': record.getMessage(),
            'extra': getattr(record, 'extra', {})
        }
        return json.dumps(log_data, ensure_ascii=False)

security_handler.setFormatter(JSONFormatter())
security_logger.addHandler(security_handler)


# Configure audit logger (for compliance)
audit_logger = logging.getLogger('audit')
audit_logger.setLevel(logging.INFO)

# Try to use file handler, fallback to console if permission denied
try:
    if logs_dir:
        audit_handler = RotatingFileHandler(
            os.path.join(logs_dir, 'audit.log'),
            maxBytes=10*1024*1024,
            backupCount=10,
            encoding='utf-8'
        )
    else:
        raise PermissionError("Logs directory not writable")
except (PermissionError, OSError) as e:
    # Fallback to console logging
    audit_handler = logging.StreamHandler()
    audit_logger.warning(f"File logging disabled, using console: {e}")

audit_handler.setFormatter(JSONFormatter())
audit_logger.addHandler(audit_handler)


def log_security_event(
    event_type: str,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: str = "INFO"
):
    """
    Log a security event.

    Args:
        event_type: Type of event (login_failed, password_changed, etc.)
        user_id: User ID if applicable
        username: Username if applicable
        ip_address: Client IP address
        details: Additional details as dict
        severity: INFO, WARNING, ERROR, CRITICAL
    """
    extra_data = {
        'event_type': event_type,
        'user_id': user_id,
        'username': username,
        'ip_address': ip_address,
        'details': details or {}
    }

    message = f"{event_type}"
    if username:
        message += f" - User: {username}"
    if ip_address:
        message += f" - IP: {ip_address}"

    log_func = getattr(security_logger, severity.lower(), security_logger.info)
    log_func(message, extra={'extra': extra_data})


def log_audit_event(
    action: str,
    user_id: int,
    username: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    changes: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None
):
    """
    Log an audit trail event for compliance.

    Args:
        action: Action performed (CREATE, UPDATE, DELETE, VIEW)
        user_id: User performing action
        username: Username
        resource_type: Type of resource (user, exam, question, etc.)
        resource_id: ID of resource
        changes: What was changed (before/after)
        ip_address: Client IP
    """
    extra_data = {
        'action': action,
        'user_id': user_id,
        'username': username,
        'resource_type': resource_type,
        'resource_id': resource_id,
        'changes': changes or {},
        'ip_address': ip_address
    }

    message = f"{action} {resource_type}"
    if resource_id:
        message += f" #{resource_id}"
    message += f" by {username}"

    audit_logger.info(message, extra={'extra': extra_data})


# Predefined event types for consistency
class SecurityEventType:
    # Authentication
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_EXPIRED = "token_expired"

    # Password
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET_REQUESTED = "password_reset_requested"
    PASSWORD_RESET_COMPLETED = "password_reset_completed"
    WEAK_PASSWORD_REJECTED = "weak_password_rejected"

    # Account
    ACCOUNT_CREATED = "account_created"
    ACCOUNT_UPDATED = "account_updated"
    ACCOUNT_DELETED = "account_deleted"
    ACCOUNT_LOCKED = "account_locked"
    ACCOUNT_UNLOCKED = "account_unlocked"

    # Role & Permissions
    ROLE_CHANGED = "role_changed"
    PERMISSION_DENIED = "permission_denied"
    UNAUTHORIZED_ACCESS = "unauthorized_access"

    # Exam Management
    EXAM_CREATED = "exam_created"
    EXAM_UPDATED = "exam_updated"
    EXAM_DELETED = "exam_deleted"
    EXAM_PUBLISHED = "exam_published"
    EXAM_UNPUBLISHED = "exam_unpublished"

    # System
    SETTINGS_CHANGED = "settings_changed"
    MAINTENANCE_MODE_ENABLED = "maintenance_mode_enabled"
    MAINTENANCE_MODE_DISABLED = "maintenance_mode_disabled"
    BACKUP_CREATED = "backup_created"
    BACKUP_RESTORED = "backup_restored"

    # Security
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    FILE_UPLOAD_REJECTED = "file_upload_rejected"
    XSS_ATTEMPT_BLOCKED = "xss_attempt_blocked"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"


# Convenience functions
def log_login_success(username: str, user_id: int, ip: str):
    log_security_event(SecurityEventType.LOGIN_SUCCESS, user_id, username, ip)


def log_login_failed(username: str, ip: str, reason: str = "invalid_credentials"):
    log_security_event(
        SecurityEventType.LOGIN_FAILED,
        username=username,
        ip_address=ip,
        details={'reason': reason},
        severity="WARNING"
    )


def log_permission_denied(user_id: int, username: str, resource: str, ip: str):
    log_security_event(
        SecurityEventType.PERMISSION_DENIED,
        user_id=user_id,
        username=username,
        ip_address=ip,
        details={'resource': resource},
        severity="WARNING"
    )


def log_rate_limit_exceeded(ip: str, endpoint: str):
    log_security_event(
        SecurityEventType.RATE_LIMIT_EXCEEDED,
        ip_address=ip,
        details={'endpoint': endpoint},
        severity="WARNING"
    )


def log_suspicious_activity(description: str, ip: str, user_id: Optional[int] = None):
    log_security_event(
        SecurityEventType.SUSPICIOUS_ACTIVITY,
        user_id=user_id,
        ip_address=ip,
        details={'description': description},
        severity="ERROR"
    )
