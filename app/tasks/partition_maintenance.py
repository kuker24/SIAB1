"""
Automated exam_logs partition lifecycle maintenance.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Tuple

from celery import shared_task
from sqlalchemy import text

from app.config import settings
from app.database import async_session_maker

logger = logging.getLogger(__name__)

PARTITION_NAME_RE = re.compile(r"^exam_logs_(\d{4})_(\d{2})$")
ARCHIVE_NAME_RE = re.compile(r"^exam_logs_(\d{4})_(\d{2})_archive_(\d{8})$")


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _shift_months(base: date, delta: int) -> date:
    month_index = (base.year * 12 + (base.month - 1)) + int(delta)
    year = month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


def _month_partition_name(month_start: date) -> str:
    return f"exam_logs_{month_start.year:04d}_{month_start.month:02d}"


async def _is_exam_logs_partitioned(db) -> bool:
    result = await db.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_partitioned_table pt
                JOIN pg_class c ON c.oid = pt.partrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname = 'exam_logs'
            ) AS is_partitioned
            """
        )
    )
    return bool(result.scalar() or False)


async def _list_attached_partitions(db) -> List[str]:
    result = await db.execute(
        text(
            """
            SELECT child.relname
            FROM pg_inherits i
            JOIN pg_class parent ON parent.oid = i.inhparent
            JOIN pg_class child ON child.oid = i.inhrelid
            JOIN pg_namespace nsp ON nsp.oid = child.relnamespace
            WHERE parent.relname = 'exam_logs'
              AND nsp.nspname = 'public'
            ORDER BY child.relname
            """
        )
    )
    return [str(row[0]) for row in result.fetchall()]


async def _list_archive_tables(db) -> List[str]:
    result = await db.execute(
        text(
            """
            SELECT c.relname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind = 'r'
              AND c.relname LIKE 'exam_logs\\_%\\_archive\\_%' ESCAPE '\\'
            ORDER BY c.relname
            """
        )
    )
    return [str(row[0]) for row in result.fetchall()]


async def _ensure_future_partitions(db, months_ahead: int) -> int:
    created = 0
    months_ahead = max(1, int(months_ahead or 1))
    today_floor = _month_floor(datetime.now(timezone.utc).date())

    for idx in range(months_ahead + 1):
        month_start = _shift_months(today_floor, idx)
        month_end = _shift_months(month_start, 1)
        partition_name = _month_partition_name(month_start)
        start_iso = month_start.isoformat()
        end_iso = month_end.isoformat()
        await db.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS public."{partition_name}"
                PARTITION OF public.exam_logs
                FOR VALUES FROM ('{start_iso}') TO ('{end_iso}')
                """
            )
        )
        created += 1
    return created


async def _detach_old_partitions(
    db,
    partitions: List[str],
    *,
    retention_months: int,
) -> Tuple[int, List[str]]:
    detached_names: List[str] = []
    retention_months = max(1, int(retention_months or 1))
    cutoff = _shift_months(_month_floor(datetime.now(timezone.utc).date()), -retention_months)
    archive_suffix = datetime.now(timezone.utc).strftime("%Y%m%d")

    for partition_name in partitions:
        match = PARTITION_NAME_RE.match(partition_name)
        if not match:
            continue

        part_year = int(match.group(1))
        part_month = int(match.group(2))
        part_start = date(part_year, part_month, 1)
        if part_start >= cutoff:
            continue

        archive_name = f"{partition_name}_archive_{archive_suffix}"
        await db.execute(
            text(f'ALTER TABLE public.exam_logs DETACH PARTITION public."{partition_name}"')
        )
        await db.execute(
            text(f'ALTER TABLE public."{partition_name}" RENAME TO "{archive_name}"')
        )
        detached_names.append(archive_name)

    return len(detached_names), detached_names


async def _drop_expired_archives(db, archive_tables: List[str], archive_retention_days: int) -> int:
    archive_retention_days = max(1, int(archive_retention_days or 1))
    cutoff_date = datetime.now(timezone.utc).date() - timedelta(days=archive_retention_days)
    dropped = 0
    for table_name in archive_tables:
        match = ARCHIVE_NAME_RE.match(table_name)
        if not match:
            continue
        try:
            archived_on = datetime.strptime(match.group(3), "%Y%m%d").date()
        except Exception:
            continue
        if archived_on > cutoff_date:
            continue
        await db.execute(text(f'DROP TABLE IF EXISTS public."{table_name}"'))
        dropped += 1
    return dropped


async def run_partition_maintenance() -> Dict[str, object]:
    if not settings.exam_logs_partition_maintenance_enabled:
        return {
            "status": "disabled",
            "reason": "EXAM_LOGS_PARTITION_MAINTENANCE_ENABLED=false",
        }

    async with async_session_maker() as db:
        is_partitioned = await _is_exam_logs_partitioned(db)
        if not is_partitioned:
            return {"status": "skipped", "reason": "exam_logs not partitioned"}

        ensured = await _ensure_future_partitions(
            db,
            months_ahead=int(settings.exam_logs_partition_months_ahead),
        )
        partitions = await _list_attached_partitions(db)
        detached_count, detached_names = await _detach_old_partitions(
            db,
            partitions,
            retention_months=int(settings.exam_logs_partition_retention_months),
        )
        archives = await _list_archive_tables(db)
        dropped_archives = await _drop_expired_archives(
            db,
            archives,
            int(settings.exam_logs_archive_retention_days),
        )
        await db.commit()

    summary: Dict[str, object] = {
        "status": "ok",
        "ensured_partition_count": ensured,
        "detached_partition_count": detached_count,
        "detached_partitions": detached_names,
        "dropped_archive_count": dropped_archives,
    }
    return summary


@shared_task(name="app.tasks.partition_maintenance.maintain_exam_logs_partitions")
def maintain_exam_logs_partitions() -> Dict[str, object]:
    """
    Celery entry point: maintain future partitions and retention lifecycle.
    """
    try:
        result = asyncio.run(run_partition_maintenance())
        logger.info("exam_logs partition maintenance completed: %s", result)
        return result
    except Exception as exc:
        logger.error("exam_logs partition maintenance failed: %s", exc, exc_info=True)
        raise
