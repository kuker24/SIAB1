from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta, timezone
from typing import List, Tuple
from zoneinfo import ZoneInfo


APP_TIMEZONE = ZoneInfo("Asia/Jakarta")


def display_question_number(order_index: int | None, fallback_position: int) -> int:
    """Return display-friendly question number without double-offsetting 1-based indexes."""
    if isinstance(order_index, int) and order_index > 0:
        return order_index
    return fallback_position


def build_local_day_windows(
    days: int,
    *,
    now: datetime | None = None,
    tz: ZoneInfo = APP_TIMEZONE,
) -> List[Tuple[str, datetime, datetime]]:
    """
    Build day buckets aligned to local calendar boundaries.

    Returns tuples of `(label, day_start_utc, day_end_utc)`.
    """
    if days < 1:
        raise ValueError("days must be >= 1")

    current_utc = now or datetime.now(timezone.utc)
    current_local = current_utc.astimezone(tz)
    oldest_local_day = current_local.date() - timedelta(days=days - 1)

    windows: List[Tuple[str, datetime, datetime]] = []
    for offset in range(days):
        local_day = oldest_local_day + timedelta(days=offset)
        day_start_utc = datetime.combine(
            local_day,
            dt_time.min,
            tzinfo=tz,
        ).astimezone(timezone.utc)
        day_end_utc = datetime.combine(
            local_day + timedelta(days=1),
            dt_time.min,
            tzinfo=tz,
        ).astimezone(timezone.utc)
        windows.append((local_day.strftime("%Y-%m-%d"), day_start_utc, day_end_utc))

    return windows
