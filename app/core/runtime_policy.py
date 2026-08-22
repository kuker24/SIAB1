"""APK/mobile runtime policy builder.

This policy is intentionally small and safe to expose to APK/web clients. It lets
operators change sync intervals through server-side runtime modes without
rebuilding the APK.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal

from app.config import settings
from app.core.degrade_mode import get_runtime_policy as get_internal_runtime_policy

RuntimeMode = Literal["normal", "busy", "exam_peak", "degraded", "maintenance"]

CRITICAL_VIOLATION_TYPES = frozenset(
    {
        "violation_apk_tampering",
        "violation_screenshot_attempt",
        "violation_screen_recording",
        "violation_external_display",
        "violation_devtools_open",
        "violation_copy",
        "violation_paste",
        "violation_clipboard_violation",
    }
)

NON_CRITICAL_DEGRADED_VIOLATION_TYPES = frozenset(
    {
        "violation_tab_switch",
        "violation_tab_switch_minor",
        "violation_focus_lost",
        "violation_browser_minimize",
        "violation_right_click",
        "violation_cut",
        "violation_overlay_app",
        "violation_accessibility_risk",
        "violation_security_warning",
    }
)

_POLICY_BY_MODE: Dict[str, Dict[str, Any]] = {
    "normal": {
        "answer_sync_interval_seconds": 15,
        "answer_sync_batch_size": 30,
        "command_poll_seconds": 25,
        "violation_flush_seconds": 30,
        "retry_after_seconds": 8,
    },
    "busy": {
        "answer_sync_interval_seconds": 25,
        "answer_sync_batch_size": 40,
        "command_poll_seconds": 35,
        "violation_flush_seconds": 60,
        "retry_after_seconds": 8,
    },
    "exam_peak": {
        "answer_sync_interval_seconds": 45,
        "answer_sync_batch_size": 50,
        "command_poll_seconds": 60,
        "violation_flush_seconds": 120,
        "retry_after_seconds": 8,
    },
    "degraded": {
        "answer_sync_interval_seconds": 45,
        "answer_sync_batch_size": 50,
        "command_poll_seconds": 60,
        "violation_flush_seconds": 120,
        "retry_after_seconds": 8,
    },
    "maintenance": {
        "answer_sync_interval_seconds": 60,
        "answer_sync_batch_size": 20,
        "command_poll_seconds": 60,
        "violation_flush_seconds": 120,
        "retry_after_seconds": 15,
    },
}


def resolve_mobile_runtime_mode(internal_policy: Dict[str, Any]) -> RuntimeMode:
    """Map internal resource/degrade flags to APK-facing runtime modes.

    Emergency resource/degrade state intentionally overrides EXAM_PEAK_MODE so
    APK clients can pause non-critical cheating telemetry when the VPS is under
    pressure. Answer save and final submit remain priority paths.
    """
    resource_mode = str(internal_policy.get("resource_mode") or "normal").strip().lower()
    degrade_mode = bool(internal_policy.get("degrade_mode", False))

    if resource_mode == "extreme":
        return "degraded"
    if resource_mode == "high" or degrade_mode:
        return "busy"
    if settings.exam_peak_mode:
        return "exam_peak"
    return "normal"


def build_mobile_runtime_policy(
    mode: RuntimeMode,
    *,
    internal_policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the stable APK-facing policy response."""
    normalized_mode = mode if mode in _POLICY_BY_MODE else "normal"
    values = dict(_POLICY_BY_MODE[normalized_mode])
    internal_policy = internal_policy or {}
    suppress_non_critical = normalized_mode in {"busy", "degraded", "maintenance"}

    values.update(
        {
            "mode": normalized_mode,
            "cheating_detection_enabled": True,
            "cheating_detail_level": "critical_only" if suppress_non_critical else "aggregate",
            "cheating_reporting_mode": "critical_only" if suppress_non_critical else "normal",
            "disabled_violation_types": sorted(NON_CRITICAL_DEGRADED_VIOLATION_TYPES)
            if suppress_non_critical
            else [],
            "critical_violation_types": sorted(CRITICAL_VIOLATION_TYPES),
            "force_submit_on_violation_enabled": True,
            "final_submit_priority": True,
            "server_time": datetime.now(timezone.utc).isoformat(),
            "policy_version": "20260606-mobile-runtime-adaptive-v2",
            "source": "server_runtime_policy",
            "resource_mode": internal_policy.get("resource_mode", "normal"),
            "degrade_mode": bool(internal_policy.get("degrade_mode", False)),
            "expires_at": internal_policy.get("resource_mode_expires_at") or internal_policy.get("expires_at"),
        }
    )
    return values


def is_violation_disabled_by_mobile_policy(
    event_type: str,
    policy: Dict[str, Any],
) -> bool:
    """Return True when a normalized violation is temporarily non-critical."""
    normalized = str(event_type or "").strip().lower()
    if not normalized:
        return False
    if not normalized.startswith("violation_"):
        normalized = f"violation_{normalized}"
    disabled = policy.get("disabled_violation_types") or []
    return normalized in {str(item).strip().lower() for item in disabled}


async def get_mobile_runtime_policy(force_refresh: bool = False) -> Dict[str, Any]:
    """Return APK/web policy with safe fallback when Redis/degrade state is unavailable."""
    try:
        internal_policy = await get_internal_runtime_policy(force_refresh=force_refresh)
    except Exception:
        internal_policy = {"resource_mode": "normal", "degrade_mode": False}

    mode = resolve_mobile_runtime_mode(internal_policy)
    return build_mobile_runtime_policy(mode, internal_policy=internal_policy)
