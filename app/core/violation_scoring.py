"""
Violation scoring policy and helpers.

This module centralizes scoring decisions for violation events so API routes
stay focused on transport/orchestration concerns.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
from typing import Any, Dict, Mapping, Optional, Tuple, FrozenSet

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import ExamLog


VIOLATION_NON_SCORING_EVENT_TYPES: FrozenSet[str] = frozenset(
    {
        "violation_right_click",
        "violation_focus_lost",
    }
)

# Explicitly disabled violation types (ignored entirely by scoring path).
VIOLATION_DISABLED_EVENT_TYPES: FrozenSet[str] = frozenset(
    {
        "violation_security_warning",
        "violation_accessibility_risk",
    }
)
VIOLATION_DISABLED_EVENT_TYPES_SQL: Tuple[str, ...] = tuple(sorted(VIOLATION_DISABLED_EVENT_TYPES))

TAB_SWITCH_WINDOW_SECONDS = 60
TAB_SWITCH_BURST_MIN_EVENTS = 3
TAB_SWITCH_MIN_DURATION_SECONDS = 3.0

ACCESSIBILITY_STRONG_SIGNAL_WINDOW_SECONDS = 180
ACCESSIBILITY_BORDERLINE_MARKERS = {
    "com.edgepro.controlcenter.freess",
}
ACCESSIBILITY_VENDOR_ALLOWLIST_MARKERS = {
    "com.samsung.accessibility/.assistantmenu.serviceframework.assistantmenuservice",
    "com.samsung.accessibility",
}
ACCESSIBILITY_HIGH_RISK_MARKERS = {
    "com.truedevelopersstudio.automatictap.autoclicker",
    "autoclicker",
}
ACCESSIBILITY_STRONG_COMPANION_EVENT_TYPES = (
    "violation_overlay_app",
    "violation_screen_recording",
    "violation_external_display",
    "violation_screenshot_attempt",
    "violation_clipboard_violation",
    "violation_copy",
    "violation_paste",
    "violation_devtools_open",
    "violation_apk_tampering",
)


def is_violation_event_disabled(normalized_event_type: str) -> bool:
    return str(normalized_event_type or "").strip().lower() in VIOLATION_DISABLED_EVENT_TYPES


def _to_lower_payload_blob(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        return ""
    parts: list[str] = []
    for key in (
        "details",
        "package_name",
        "package",
        "service",
        "services",
        "accessibility_service",
    ):
        value = payload.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend([str(item) for item in value])
    if not parts:
        try:
            parts.append(json.dumps(dict(payload), ensure_ascii=False))
        except Exception:
            parts.append(str(payload))
    return " ".join(parts).strip().lower()


def _extract_tab_switch_duration_seconds(payload: Mapping[str, Any]) -> Optional[float]:
    if not isinstance(payload, Mapping):
        return None

    for key in ("duration_seconds", "duration_sec", "time_away_seconds", "duration"):
        raw = payload.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
            if value >= 0:
                return value
        except (TypeError, ValueError):
            continue

    details = str(payload.get("details") or "")
    if details:
        left_app_match = re.search(
            r"left\s+app\s+for\s+([0-9]+(?:\.[0-9]+)?)\s*s",
            details,
            re.IGNORECASE,
        )
        if left_app_match:
            return float(left_app_match.group(1))

        generic_match = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s*s\b", details, re.IGNORECASE)
        if generic_match:
            return float(generic_match.group(1))
    return None


async def _count_recent_violation_events(
    db: AsyncSession,
    *,
    session_id: int,
    event_type: str,
    since_at: datetime,
) -> int:
    result = await db.execute(
        select(func.count(ExamLog.id)).where(
            ExamLog.session_id == session_id,
            ExamLog.event_type == event_type,
            ExamLog.created_at >= since_at,
        )
    )
    return int(result.scalar() or 0)


async def _has_recent_strong_companion_signals(
    db: AsyncSession,
    *,
    session_id: int,
    since_at: datetime,
) -> bool:
    result = await db.execute(
        select(func.count(ExamLog.id)).where(
            ExamLog.session_id == session_id,
            ExamLog.event_type.in_(ACCESSIBILITY_STRONG_COMPANION_EVENT_TYPES),
            ExamLog.created_at >= since_at,
        )
    )
    return int(result.scalar() or 0) > 0


async def should_count_violation_for_score(
    db: AsyncSession,
    *,
    session_id: int,
    normalized_event_type: str,
    violation_payload: Dict[str, Any],
    reported_at: datetime,
) -> Tuple[bool, str]:
    """
    Return (should_count, counting_policy) for a normalized violation event type.
    """
    event_type = str(normalized_event_type or "").strip().lower()
    payload: Dict[str, Any] = dict(violation_payload or {})

    if event_type in VIOLATION_NON_SCORING_EVENT_TYPES:
        return False, f"{event_type}_warning_only"

    if event_type == "violation_tab_switch":
        duration_seconds = _extract_tab_switch_duration_seconds(payload)
        if duration_seconds is not None and duration_seconds >= TAB_SWITCH_MIN_DURATION_SECONDS:
            return True, "tab_switch_duration_threshold"

        recent_count = await _count_recent_violation_events(
            db,
            session_id=session_id,
            event_type="violation_tab_switch",
            since_at=reported_at - timedelta(seconds=TAB_SWITCH_WINDOW_SECONDS),
        )
        if (recent_count + 1) >= TAB_SWITCH_BURST_MIN_EVENTS:
            return True, "tab_switch_burst_threshold"
        return False, "tab_switch_minor_filtered"

    if event_type == "violation_accessibility_risk":
        details_blob = _to_lower_payload_blob(payload)
        has_samsung_allowlist = any(
            marker in details_blob for marker in ACCESSIBILITY_VENDOR_ALLOWLIST_MARKERS
        )
        has_edgepro_borderline = any(
            marker in details_blob for marker in ACCESSIBILITY_BORDERLINE_MARKERS
        )
        has_high_risk_marker = any(marker in details_blob for marker in ACCESSIBILITY_HIGH_RISK_MARKERS)

        if has_samsung_allowlist and not has_high_risk_marker and not has_edgepro_borderline:
            return False, "accessibility_vendor_allowlist"

        if has_edgepro_borderline and not has_high_risk_marker:
            has_companion = await _has_recent_strong_companion_signals(
                db,
                session_id=session_id,
                since_at=reported_at - timedelta(seconds=ACCESSIBILITY_STRONG_SIGNAL_WINDOW_SECONDS),
            )
            if not has_companion:
                return False, "accessibility_borderline_warning_only"
            return True, "accessibility_borderline_with_strong_companion"

    return True, "default"
