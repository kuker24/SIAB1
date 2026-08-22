"""
Security Event Analytics API
Provides analytics and reporting for security events, failed logins, and suspicious activities.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel

from app.database import get_db
from app.core.security import get_current_active_admin
from app.models.user import User
from app.core.account_lockout import get_lockout
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/security", tags=["security-analytics"])


# === Schemas ====

class FailedLoginStats(BaseModel):
    total_failures: int
    unique_users: int
    unique_ips: int
    top_users: List[Dict[str, Any]]
    top_ips: List[Dict[str, Any]]
    timeline: Dict[str, int]
    currently_locked: int


class SecurityEvent(BaseModel):
    id: int
    event_type: str
    user_id: Optional[int]
    username: Optional[str]
    ip_address: Optional[str]
    severity: str
    timestamp: datetime
    extra_data: Optional[str]


class SecurityOverview(BaseModel):
    failed_logins_24h: int
    account_lockouts_24h: int
    security_events_24h: int
    apk_tampering_24h: int
    currently_locked_accounts: int
    high_severity_events: int


# === Endpoints ===

@router.get("/overview")
async def get_security_overview(
    hours: int = Query(24, description="Time window in hours"),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
) -> SecurityOverview:
    """
    Get security overview statistics for the specified time window.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get failed login attempts from security_events table
    result = await db.execute(text("""
        SELECT COUNT(*) as count
        FROM security_events
        WHERE event_type = 'failed_login'
        AND timestamp > :since
    """), {"since": since})
    failed_logins = result.scalar() or 0

    # Get account lockouts
    result = await db.execute(text("""
        SELECT COUNT(*) as count
        FROM security_events
        WHERE event_type = 'account_locked'
        AND timestamp > :since
    """), {"since": since})
    account_lockouts = result.scalar() or 0

    # Get total security events
    result = await db.execute(text("""
        SELECT COUNT(*) as count
        FROM security_events
        WHERE timestamp > :since
    """), {"since": since})
    total_events = result.scalar() or 0

    # Get APK tampering attempts
    result = await db.execute(text("""
        SELECT COUNT(*) as count
        FROM security_events
        WHERE event_type = 'apk_tampering'
        AND timestamp > :since
    """), {"since": since})
    apk_tampering = result.scalar() or 0

    # Get currently locked accounts from Redis
    lockout = get_lockout()
    locked_accounts = await lockout.get_all_locked()

    # Get high severity events
    result = await db.execute(text("""
        SELECT COUNT(*) as count
        FROM security_events
        WHERE severity IN ('high', 'critical')
        AND timestamp > :since
    """), {"since": since})
    high_severity = result.scalar() or 0

    return SecurityOverview(
        failed_logins_24h=failed_logins,
        account_lockouts_24h=account_lockouts,
        security_events_24h=total_events,
        apk_tampering_24h=apk_tampering,
        currently_locked_accounts=len(locked_accounts),
        high_severity_events=high_severity
    )


@router.get("/failed-logins")
async def get_failed_login_analytics(
    hours: int = Query(24, description="Time window in hours"),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
) -> FailedLoginStats:
    """
    Get detailed analytics for failed login attempts.
    Includes top users, top IPs, and timeline breakdown.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Total failures
    result = await db.execute(text("""
        SELECT COUNT(*) as total
        FROM security_events
        WHERE event_type = 'failed_login'
        AND timestamp > :since
    """), {"since": since})
    total_failures = result.scalar() or 0

    # Unique users affected
    result = await db.execute(text("""
        SELECT COUNT(DISTINCT user_id) as count
        FROM security_events
        WHERE event_type = 'failed_login'
        AND timestamp > :since
        AND user_id IS NOT NULL
    """), {"since": since})
    unique_users = result.scalar() or 0

    # Unique IPs
    result = await db.execute(text("""
        SELECT COUNT(DISTINCT ip_address) as count
        FROM security_events
        WHERE event_type = 'failed_login'
        AND timestamp > :since
        AND ip_address IS NOT NULL
    """), {"since": since})
    unique_ips = result.scalar() or 0

    # Top users by failure count
    result = await db.execute(text("""
        SELECT
            u.username,
            u.full_name,
            u.role,
            COUNT(*) as failure_count
        FROM security_events se
        LEFT JOIN users u ON se.user_id = u.id
        WHERE se.event_type = 'failed_login'
        AND se.timestamp > :since
        AND u.username IS NOT NULL
        GROUP BY u.username, u.full_name, u.role
        ORDER BY failure_count DESC
        LIMIT 10
    """), {"since": since})
    top_users = [
        {
            "username": row[0],
            "full_name": row[1],
            "role": row[2],
            "count": row[3]
        }
        for row in result
    ]

    # Top IPs by failure count
    result = await db.execute(text("""
        SELECT
            ip_address,
            COUNT(*) as failure_count
        FROM security_events
        WHERE event_type = 'failed_login'
        AND timestamp > :since
        AND ip_address IS NOT NULL
        GROUP BY ip_address
        ORDER BY failure_count DESC
        LIMIT 10
    """), {"since": since})
    top_ips = [
        {
            "ip": row[0],
            "count": row[1]
        }
        for row in result
    ]

    # Timeline breakdown (hourly)
    result = await db.execute(text("""
        SELECT
            date_trunc('hour', timestamp) as hour,
            COUNT(*) as count
        FROM security_events
        WHERE event_type = 'failed_login'
        AND timestamp > :since
        GROUP BY hour
        ORDER BY hour
    """), {"since": since})
    timeline = {
        row[0].strftime("%Y-%m-%d %H:00"): row[1]
        for row in result
    }

    # Currently locked accounts
    lockout = get_lockout()
    locked_accounts = await lockout.get_all_locked()

    return FailedLoginStats(
        total_failures=total_failures,
        unique_users=unique_users,
        unique_ips=unique_ips,
        top_users=top_users,
        top_ips=top_ips,
        timeline=timeline,
        currently_locked=len(locked_accounts)
    )


@router.get("/events")
async def get_security_events(
    hours: int = Query(24, description="Time window in hours"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    limit: int = Query(100, description="Maximum events to return"),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
) -> List[SecurityEvent]:
    """
    Get recent security events with optional filtering.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = """
        SELECT
            se.id,
            se.event_type,
            se.user_id,
            u.username,
            se.ip_address,
            se.severity,
            se.timestamp,
            se.extra_data
        FROM security_events se
        LEFT JOIN users u ON se.user_id = u.id
        WHERE se.timestamp > :since
    """

    params = {"since": since}

    if event_type:
        query += " AND se.event_type = :event_type"
        params["event_type"] = event_type

    if severity:
        query += " AND se.severity = :severity"
        params["severity"] = severity

    query += " ORDER BY se.timestamp DESC LIMIT :limit"
    params["limit"] = limit

    result = await db.execute(text(query), params)

    events = []
    for row in result:
        events.append(SecurityEvent(
            id=row[0],
            event_type=row[1],
            user_id=row[2],
            username=row[3],
            ip_address=row[4],
            severity=row[5],
            timestamp=row[6],
            extra_data=row[7]
        ))

    return events


@router.get("/analytics/locked-accounts")
async def get_locked_accounts(
    current_user: User = Depends(get_current_active_admin)
) -> List[Dict[str, Any]]:
    """
    Get all currently locked accounts from Redis.
    """
    lockout = get_lockout()
    locked_accounts = await lockout.get_all_locked()
    return locked_accounts


@router.post("/analytics/unlock/{username}")
async def unlock_account(
    username: str,
    current_user: User = Depends(get_current_active_admin)
) -> Dict[str, Any]:
    """
    Manually unlock a specific account.
    """
    lockout = get_lockout()
    was_locked = await lockout.admin_unlock(username, current_user.username)

    if was_locked:
        return {
            "success": True,
            "message": f"Account '{username}' has been unlocked"
        }
    else:
        return {
            "success": False,
            "message": f"Account '{username}' was not locked"
        }


@router.get("/attack-patterns")
async def detect_attack_patterns(
    hours: int = Query(24, description="Time window in hours"),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Detect potential attack patterns:
    - Brute force attacks (multiple failures from same IP)
    - Distributed attacks (failures from multiple IPs to same user)
    - Credential stuffing (failures across multiple users from same IP)
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Potential brute force (>10 failures from single IP)
    result = await db.execute(text("""
        SELECT
            ip_address,
            COUNT(*) as attempt_count,
            COUNT(DISTINCT user_id) as unique_users
        FROM security_events
        WHERE event_type = 'failed_login'
        AND timestamp > :since
        AND ip_address IS NOT NULL
        GROUP BY ip_address
        HAVING COUNT(*) > 10
        ORDER BY attempt_count DESC
        LIMIT 10
    """), {"since": since})
    brute_force = [
        {
            "ip": row[0],
            "attempts": row[1],
            "unique_users_targeted": row[2],
            "pattern": "brute_force"
        }
        for row in result
    ]

    # Distributed attacks (single user targeted from multiple IPs)
    result = await db.execute(text("""
        SELECT
            u.username,
            COUNT(DISTINCT se.ip_address) as unique_ips,
            COUNT(*) as total_attempts
        FROM security_events se
        JOIN users u ON se.user_id = u.id
        WHERE se.event_type = 'failed_login'
        AND se.timestamp > :since
        GROUP BY u.username
        HAVING COUNT(DISTINCT se.ip_address) > 5
        ORDER BY unique_ips DESC
        LIMIT 10
    """), {"since": since})
    distributed = [
        {
            "username": row[0],
            "source_ips": row[1],
            "attempts": row[2],
            "pattern": "distributed_attack"
        }
        for row in result
    ]

    return {
        "brute_force_attacks": brute_force,
        "distributed_attacks": distributed,
        "detected_at": datetime.now(timezone.utc).isoformat()
    }
