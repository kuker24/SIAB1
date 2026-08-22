"""
User Activity Logging API endpoints.
Dashboard and audit trail for user activities.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.security import get_current_active_admin, get_current_user
from app.database import get_db, get_db_write
from app.models.activity_log import UserActivityLog
from app.models.user import User

router = APIRouter(prefix="/api/activity", tags=["Activity Logs"])
logger = logging.getLogger(__name__)

# WIB timezone constant (UTC+7)
WIB = timezone(timedelta(hours=7))

_auto_prune_lock = asyncio.Lock()
_last_auto_prune_run_utc: Optional[datetime] = None


def format_timestamp_wib(dt: datetime) -> Optional[str]:
    """
    Convert datetime to WIB timezone and return ISO format string.

    Handles two cases:
    1. Naive datetime: For legacy data stored without timezone info.
       In Docker with TZ=Asia/Jakarta, naive datetimes ARE already in WIB.
    2. Timezone-aware datetime: Properly convert to WIB.
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        # Naive datetime - assume it's already in WIB (container local time)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+07:00")

    dt_wib = dt.astimezone(WIB)
    return dt_wib.strftime("%Y-%m-%dT%H:%M:%S+07:00")


async def _count_activity_logs(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(UserActivityLog.id)))
    return int(result.scalar() or 0)


async def _delete_activity_logs_older_than(
    db: AsyncSession,
    *,
    cutoff_utc: datetime,
    limit: int,
) -> int:
    if limit <= 0:
        return 0

    stale_ids_subquery = (
        select(UserActivityLog.id)
        .where(UserActivityLog.created_at < cutoff_utc)
        .order_by(UserActivityLog.created_at.asc(), UserActivityLog.id.asc())
        .limit(limit)
        .subquery()
    )
    result = await db.execute(
        delete(UserActivityLog).where(
            UserActivityLog.id.in_(select(stale_ids_subquery.c.id))
        )
    )
    return max(0, int(result.rowcount or 0))


async def _delete_oldest_activity_logs(db: AsyncSession, *, limit: int) -> int:
    if limit <= 0:
        return 0

    oldest_ids_subquery = (
        select(UserActivityLog.id)
        .order_by(UserActivityLog.created_at.asc(), UserActivityLog.id.asc())
        .limit(limit)
        .subquery()
    )
    result = await db.execute(
        delete(UserActivityLog).where(
            UserActivityLog.id.in_(select(oldest_ids_subquery.c.id))
        )
    )
    return max(0, int(result.rowcount or 0))


async def _smart_prune_activity_logs(
    db: AsyncSession,
    *,
    retention_days: int,
    max_rows: int,
    batch_size: int,
    max_rounds: int = 1,
) -> dict[str, Any]:
    """Delete stale/overflow logs in bounded batches."""
    safe_retention_days = max(0, int(retention_days))
    safe_max_rows = max(1000, int(max_rows))
    safe_batch_size = max(100, int(batch_size))
    safe_rounds = max(1, int(max_rounds))

    total_before = await _count_activity_logs(db)
    deleted_by_age = 0
    deleted_by_cap = 0
    rounds = 0

    cutoff_utc: Optional[datetime] = None
    if safe_retention_days > 0:
        cutoff_utc = datetime.now(timezone.utc) - timedelta(days=safe_retention_days)

    for _ in range(safe_rounds):
        rounds += 1
        deleted_this_round = 0

        if cutoff_utc is not None:
            deleted_now = await _delete_activity_logs_older_than(
                db,
                cutoff_utc=cutoff_utc,
                limit=safe_batch_size,
            )
            deleted_by_age += deleted_now
            deleted_this_round += deleted_now

        current_total = await _count_activity_logs(db)
        overflow = max(0, current_total - safe_max_rows)
        if overflow > 0:
            cap_delete_limit = min(safe_batch_size, overflow)
            deleted_now = await _delete_oldest_activity_logs(db, limit=cap_delete_limit)
            deleted_by_cap += deleted_now
            deleted_this_round += deleted_now

        if deleted_this_round == 0:
            break

    remaining_total = await _count_activity_logs(db)
    deleted_total = deleted_by_age + deleted_by_cap

    return {
        "deleted_total": deleted_total,
        "deleted_by_age": deleted_by_age,
        "deleted_by_cap": deleted_by_cap,
        "before_total": total_before,
        "remaining_total": remaining_total,
        "retention_days": safe_retention_days,
        "max_rows": safe_max_rows,
        "batch_size": safe_batch_size,
        "rounds": rounds,
    }


async def _maybe_auto_prune_activity_logs(db: AsyncSession) -> None:
    """
    Opportunistic cleanup so activity table does not keep growing forever.
    Runs at most once per worker per configured interval.
    """
    if not settings.activity_log_auto_prune_enabled:
        return

    interval_seconds = max(60, int(settings.activity_log_auto_prune_interval_seconds))
    now_utc = datetime.now(timezone.utc)

    global _last_auto_prune_run_utc
    if _last_auto_prune_run_utc and (
        now_utc - _last_auto_prune_run_utc
    ).total_seconds() < interval_seconds:
        return

    async with _auto_prune_lock:
        now_utc = datetime.now(timezone.utc)
        if _last_auto_prune_run_utc and (
            now_utc - _last_auto_prune_run_utc
        ).total_seconds() < interval_seconds:
            return

        try:
            report = await _smart_prune_activity_logs(
                db,
                retention_days=settings.activity_log_retention_days,
                max_rows=settings.activity_log_max_rows,
                batch_size=settings.activity_log_prune_batch_size,
                max_rounds=1,
            )
            _last_auto_prune_run_utc = now_utc
            if report["deleted_total"] > 0:
                logger.info(
                    "Auto-pruned activity logs: deleted=%s remaining=%s",
                    report["deleted_total"],
                    report["remaining_total"],
                )
        except Exception:
            logger.warning("Automatic activity log prune failed", exc_info=True)


@router.get("/logs")
async def get_activity_logs(
    user_id: Optional[int] = None,
    event_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get user activity logs with filters (admin only).

    **Filters:**
    - user_id: Filter by specific user
    - event_type: login, logout, exam_start, exam_submit, violation, etc.
    - date_from / date_to: Date range filter
    """
    await _maybe_auto_prune_activity_logs(db)

    query = select(UserActivityLog).options(selectinload(UserActivityLog.user))

    if user_id:
        query = query.where(UserActivityLog.user_id == user_id)
    if event_type:
        query = query.where(UserActivityLog.event_type == event_type)
    if date_from:
        query = query.where(UserActivityLog.created_at >= date_from)
    if date_to:
        query = query.where(UserActivityLog.created_at <= date_to)

    count_query = select(func.count()).select_from(query.subquery())
    total = int((await db.execute(count_query)).scalar() or 0)

    offset = (page - 1) * per_page
    query = query.order_by(UserActivityLog.created_at.desc()).offset(offset).limit(per_page)

    result = await db.execute(query)
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "user_name": log.user.full_name if log.user else "Unknown",
                "user_role": log.user.role if log.user else None,
                "event_type": log.event_type,
                "event_data": log.event_data,
                "ip_address": log.ip_address,
                "created_at": format_timestamp_wib(log.created_at),
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 0,
    }


@router.delete("/logs/reset")
async def reset_activity_logs(
    mode: str = Query("all", pattern="^(all|smart)$"),
    retention_days: int = Query(14, ge=1, le=3650),
    max_rows: int = Query(50000, ge=1000, le=1000000),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db_write),
):
    """
    Reset or cleanup activity logs (admin only).

    - mode=all: clear all activity logs (fast truncate)
    - mode=smart: keep only recent/limited records
    """
    total_before = await _count_activity_logs(db)

    if mode == "all":
        await db.execute(text("TRUNCATE TABLE user_activity_logs RESTART IDENTITY"))
        remaining_total = await _count_activity_logs(db)
        deleted_total = max(0, total_before - remaining_total)

        global _last_auto_prune_run_utc
        _last_auto_prune_run_utc = datetime.now(timezone.utc)

        return {
            "mode": "all",
            "deleted_total": deleted_total,
            "before_total": total_before,
            "remaining_total": remaining_total,
            "message": "All activity logs were reset",
        }

    report = await _smart_prune_activity_logs(
        db,
        retention_days=retention_days,
        max_rows=max_rows,
        batch_size=settings.activity_log_prune_batch_size,
        max_rounds=40,
    )

    _last_auto_prune_run_utc = datetime.now(timezone.utc)
    report.update(
        {
            "mode": "smart",
            "message": "Activity logs cleaned up using smart prune",
        }
    )
    return report


@router.get("/stats")
async def get_activity_stats(
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get activity statistics for dashboard."""
    try:
        await _maybe_auto_prune_activity_logs(db)

        # Calculate date range in WIB
        now_wib = datetime.now(WIB)
        start_date_wib = now_wib - timedelta(days=days)

        # Convert to UTC for database queries
        start_date_utc = start_date_wib.astimezone(timezone.utc)

        # Total activities
        total_result = await db.execute(
            select(func.count(UserActivityLog.id)).where(UserActivityLog.created_at >= start_date_utc)
        )
        total_activities = int(total_result.scalar() or 0)

        # Activities by type
        by_type_result = await db.execute(
            select(
                UserActivityLog.event_type,
                func.count(UserActivityLog.id).label("count"),
            )
            .where(UserActivityLog.created_at >= start_date_utc)
            .group_by(UserActivityLog.event_type)
        )
        by_type = {row[0]: row[1] for row in by_type_result.fetchall() if row[0]}

        # Daily trend - single grouped query in WIB timezone (avoid N queries for N days)
        day_wib_expr = func.date(func.timezone("Asia/Jakarta", UserActivityLog.created_at))
        daily_counts_result = await db.execute(
            select(
                day_wib_expr.label("day_wib"),
                func.count(UserActivityLog.id).label("count"),
            )
            .where(UserActivityLog.created_at >= start_date_utc)
            .group_by(day_wib_expr)
            .order_by(day_wib_expr)
        )
        daily_counts_map = {
            str(day_wib): int(count or 0)
            for day_wib, count in daily_counts_result.fetchall()
            if day_wib is not None
        }
        daily_trend = [
            {
                "date": (start_date_wib + timedelta(days=i)).strftime("%Y-%m-%d"),
                "count": daily_counts_map.get((start_date_wib + timedelta(days=i)).strftime("%Y-%m-%d"), 0),
            }
            for i in range(days)
        ]

        # Most active users (top 10) - single query to avoid N+1.
        top_users_result = await db.execute(
            select(
                User.id,
                User.full_name,
                func.count(UserActivityLog.id).label("activity_count"),
            )
            .join(UserActivityLog, UserActivityLog.user_id == User.id)
            .where(UserActivityLog.created_at >= start_date_utc)
            .group_by(User.id, User.full_name)
            .order_by(func.count(UserActivityLog.id).desc())
            .limit(10)
        )
        top_users = [
            {
                "user_id": user_id,
                "user_name": user_name,
                "activity_count": activity_count,
            }
            for user_id, user_name, activity_count in top_users_result.fetchall()
        ]

        return {
            "period_days": days,
            "total_activities": total_activities,
            "by_type": by_type,
            "daily_trend": daily_trend,
            "top_users": top_users,
        }
    except Exception as exc:
        logger.error("Activity stats error: %s", str(exc), exc_info=True)
        return {
            "period_days": days,
            "total_activities": 0,
            "by_type": {},
            "daily_trend": [],
            "top_users": [],
            "error": str(exc),
        }


@router.get("/event-types")
async def get_event_types(
    current_user: User = Depends(get_current_active_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get list of all event types for filtering."""
    result = await db.execute(
        select(UserActivityLog.event_type).distinct().order_by(UserActivityLog.event_type)
    )
    event_types = [row[0] for row in result.fetchall()]

    return {"event_types": event_types}


@router.get("/my-logs")
async def get_my_activity_logs(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's activity logs."""
    result = await db.execute(
        select(UserActivityLog)
        .where(UserActivityLog.user_id == current_user.id)
        .order_by(UserActivityLog.created_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()

    return {
        "logs": [
            {
                "id": log.id,
                "event_type": log.event_type,
                "event_data": log.event_data,
                "ip_address": log.ip_address,
                "created_at": format_timestamp_wib(log.created_at),
            }
            for log in logs
        ]
    }


# Helper function for logging activities (can be imported by other modules)
async def log_activity(
    db: AsyncSession,
    user_id: int,
    event_type: str,
    event_data: dict = None,
    ip_address: str = None,
):
    """
    Helper function to log user activity.

    Event types:
    - login, logout
    - exam_start, exam_submit, exam_view
    - question_create, question_update, question_delete
    - user_create, user_update, user_delete
    - violation
    - export_data

    Note: Caller must commit the transaction.
    """
    log = UserActivityLog(
        user_id=user_id,
        event_type=event_type,
        event_data=event_data or {},
        ip_address=ip_address,
    )
    db.add(log)
    return log
