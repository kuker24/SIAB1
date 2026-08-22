"""
Auto-restart scheduler with one-off multi-schedule support (WIB / Asia/Jakarta).

Behavior:
- Admin can add multiple one-off restart schedules in WIB.
- Each schedule entry is executed once (no endless recurring restart).
- Existing restart guardrails are reused from monitoring restart-safe flow.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.config import settings
from app.core.redis_pubsub import get_redis

logger = logging.getLogger(__name__)

AUTO_RESTART_SCHEDULE_KEY = "system:auto_restart_schedule"
AUTO_RESTART_STATUS_KEY = "system:auto_restart_status"
AUTO_RESTART_EXEC_LOCK_KEY = "system:auto_restart_exec_lock"
AUTO_RESTART_CACHE_TTL_SECONDS = 3
AUTO_RESTART_STATUS_CACHE_TTL_SECONDS = 3
AUTO_RESTART_MAX_ENTRIES = 200

WIB_TZ = ZoneInfo("Asia/Jakarta")
WIB_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
WIB_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T](?:[01]\d|2[0-3]):[0-5]\d(?:[:][0-5]\d)?$"
)

_cached_schedule: Optional[Dict[str, Any]] = None
_cached_schedule_at: float = 0.0
_cached_status: Optional[Dict[str, Any]] = None
_cached_status_at: float = 0.0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _decode_payload(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="ignore")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _is_fresh(ts: float, ttl_seconds: int) -> bool:
    return (time.monotonic() - ts) < ttl_seconds


def _set_schedule_cache(value: Dict[str, Any]) -> None:
    global _cached_schedule, _cached_schedule_at
    _cached_schedule = value
    _cached_schedule_at = time.monotonic()


def _set_status_cache(value: Dict[str, Any]) -> None:
    global _cached_status, _cached_status_at
    _cached_status = value
    _cached_status_at = time.monotonic()


def _invalidate_ops_summary_cache() -> None:
    try:
        from app.core.ops_summary import invalidate_ops_summary_cache

        invalidate_ops_summary_cache()
    except Exception as exc:
        logger.debug("Ops summary cache invalidate skipped: %s", exc)


def _normalize_time_wib(value: Optional[str]) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        candidate = str(getattr(settings, "auto_restart_time_wib", "00:30"))
    if not WIB_TIME_PATTERN.fullmatch(candidate):
        return "00:30"
    return candidate


def _parse_wib_datetime(value: str) -> datetime:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("Jadwal kosong.")

    # ISO with timezone support
    try:
        iso_candidate = candidate.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(iso_candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=WIB_TZ)
        parsed = parsed.astimezone(WIB_TZ)
        return parsed.replace(second=0, microsecond=0)
    except Exception:
        pass

    if not WIB_DATETIME_PATTERN.fullmatch(candidate):
        raise ValueError("Format jadwal tidak valid. Gunakan YYYY-MM-DD HH:MM (WIB).")

    normalized = candidate.replace("T", " ")
    fmt = "%Y-%m-%d %H:%M:%S" if len(normalized) == 19 else "%Y-%m-%d %H:%M"
    parsed = datetime.strptime(normalized, fmt)
    return parsed.replace(tzinfo=WIB_TZ, second=0, microsecond=0)


def _entry_id() -> str:
    return f"ar_{int(time.time() * 1000)}_{os.getpid()}_{time.time_ns() % 1000000}"


def _normalize_entry(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    entry_id = str(payload.get("id") or "").strip() or _entry_id()
    raw_wib = payload.get("scheduled_at_wib") or payload.get("scheduled_at")
    if not raw_wib:
        return None

    try:
        scheduled_wib = _parse_wib_datetime(str(raw_wib))
    except Exception:
        return None

    status = str(payload.get("status") or "pending").strip().lower()
    if status not in {"pending", "running", "success", "blocked", "failed", "cancelled"}:
        status = "pending"

    return {
        "id": entry_id,
        "scheduled_at_wib": scheduled_wib.isoformat(),
        "scheduled_at_utc": scheduled_wib.astimezone(timezone.utc).isoformat(),
        "status": status,
        "created_at": payload.get("created_at") or _now_iso(),
        "triggered_at": payload.get("triggered_at"),
        "finished_at": payload.get("finished_at"),
        "error": payload.get("error"),
        "reason": payload.get("reason"),
    }


def _entry_utc(entry: Dict[str, Any]) -> Optional[datetime]:
    value = str(entry.get("scheduled_at_utc") or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_entries(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    normalized: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw in payload:
        entry = _normalize_entry(raw if isinstance(raw, dict) else {})
        if not entry:
            continue
        if entry["id"] in seen_ids:
            continue
        seen_ids.add(entry["id"])
        normalized.append(entry)
    normalized.sort(key=lambda item: str(item.get("scheduled_at_utc") or ""))
    return normalized[-AUTO_RESTART_MAX_ENTRIES:]


def _default_schedule() -> Dict[str, Any]:
    return {
        "enabled": bool(getattr(settings, "auto_restart_enabled", False)),
        "timezone": "Asia/Jakarta",
        "time_wib": _normalize_time_wib(getattr(settings, "auto_restart_time_wib", "00:30")),
        "restart_buffer_minutes": max(5, min(int(getattr(settings, "auto_restart_buffer_minutes", 30)), 180)),
        "full_restart": bool(getattr(settings, "auto_restart_full_restart", True)),
        "include_data_services": bool(getattr(settings, "auto_restart_include_data_services", True)),
        "restart_timeout_seconds": max(
            60, min(int(getattr(settings, "auto_restart_timeout_seconds", 300)), 1200)
        ),
        "reason": "Auto restart terjadwal WIB",
        "source": "default",
        "actor": None,
        "updated_at": None,
        "entries": [],
    }


def _normalize_schedule(payload: Dict[str, Any]) -> Dict[str, Any]:
    default = _default_schedule()
    normalized = {
        "enabled": bool(payload.get("enabled", default["enabled"])),
        "timezone": "Asia/Jakarta",
        "time_wib": _normalize_time_wib(payload.get("time_wib", default["time_wib"])),
        "restart_buffer_minutes": max(
            5,
            min(int(payload.get("restart_buffer_minutes", default["restart_buffer_minutes"]) or 30), 180),
        ),
        "full_restart": bool(payload.get("full_restart", default["full_restart"])),
        "include_data_services": bool(
            payload.get("include_data_services", default["include_data_services"])
        ),
        "restart_timeout_seconds": max(
            60,
            min(int(payload.get("restart_timeout_seconds", default["restart_timeout_seconds"]) or 300), 1200),
        ),
        "reason": str(payload.get("reason") or default["reason"]).strip() or default["reason"],
        "source": str(payload.get("source") or default["source"]),
        "actor": payload.get("actor"),
        "updated_at": payload.get("updated_at"),
        "entries": _normalize_entries(payload.get("entries")),
    }
    return normalized


def _build_status_from_schedule(schedule: Dict[str, Any], now_utc: Optional[datetime] = None) -> Dict[str, Any]:
    now_utc = now_utc or _now_utc()
    entries = _normalize_entries(schedule.get("entries"))
    pending = [entry for entry in entries if str(entry.get("status")).lower() == "pending"]

    due_entries: List[Dict[str, Any]] = []
    future_entries: List[Dict[str, Any]] = []
    for entry in pending:
        scheduled_at_utc = _entry_utc(entry)
        if not scheduled_at_utc:
            continue
        if scheduled_at_utc <= now_utc:
            due_entries.append(entry)
        else:
            future_entries.append(entry)

    next_entry = None
    if future_entries:
        next_entry = min(
            future_entries,
            key=lambda item: _entry_utc(item) or datetime.max.replace(tzinfo=timezone.utc),
        )

    enabled = bool(schedule.get("enabled", False))
    if not enabled:
        state = "disabled"
        summary = "Auto restart terjadwal dinonaktifkan."
    elif due_entries:
        state = "due"
        summary = f"Ada {len(due_entries)} jadwal restart siap dieksekusi."
    elif next_entry:
        state = "scheduled"
        summary = f"Menunggu {len(pending)} jadwal restart. Next {next_entry.get('scheduled_at_wib')} WIB."
    else:
        state = "idle"
        summary = "Tidak ada jadwal restart pending."

    return {
        "enabled": enabled,
        "timezone": "Asia/Jakarta",
        "time_wib": schedule.get("time_wib", "00:30"),
        "state": state,
        "summary": summary,
        "pending_count": len(pending),
        "due_count": len(due_entries),
        "next_run_at_utc": next_entry.get("scheduled_at_utc") if next_entry else None,
        "next_run_at_wib": next_entry.get("scheduled_at_wib") if next_entry else None,
        "upcoming_entries": future_entries[:10],
        "last_checked_at": now_utc.isoformat(),
        "last_triggered_at": None,
        "last_result_at": None,
        "last_error": None,
        "last_result": None,
    }


def _upsert_status_context(status: Dict[str, Any], schedule: Dict[str, Any], now_utc: datetime) -> Dict[str, Any]:
    merged = dict(status)
    computed = _build_status_from_schedule(schedule, now_utc=now_utc)
    for key in (
        "enabled",
        "timezone",
        "time_wib",
        "pending_count",
        "due_count",
        "next_run_at_utc",
        "next_run_at_wib",
        "upcoming_entries",
        "last_checked_at",
    ):
        merged[key] = computed.get(key)
    if not str(merged.get("state") or "").strip():
        merged["state"] = computed["state"]
    if not str(merged.get("summary") or "").strip():
        merged["summary"] = computed["summary"]
    return merged


async def _persist_schedule(schedule: Dict[str, Any]) -> None:
    try:
        redis = await get_redis()
        await redis.set(AUTO_RESTART_SCHEDULE_KEY, json.dumps(schedule))
    except Exception as exc:
        logger.warning("Failed to persist auto restart schedule: %s", exc)
    _set_schedule_cache(schedule)
    _invalidate_ops_summary_cache()


async def _persist_status(status: Dict[str, Any]) -> None:
    try:
        redis = await get_redis()
        await redis.set(AUTO_RESTART_STATUS_KEY, json.dumps(status))
    except Exception as exc:
        logger.warning("Failed to persist auto restart status: %s", exc)
    _set_status_cache(status)
    _invalidate_ops_summary_cache()


async def get_auto_restart_schedule(force_refresh: bool = False) -> Dict[str, Any]:
    if (
        not force_refresh
        and _cached_schedule is not None
        and _is_fresh(_cached_schedule_at, AUTO_RESTART_CACHE_TTL_SECONDS)
    ):
        return dict(_cached_schedule)

    default = _default_schedule()
    try:
        redis = await get_redis()
        payload = _decode_payload(await redis.get(AUTO_RESTART_SCHEDULE_KEY))
        if not payload:
            _set_schedule_cache(default)
            return dict(default)
        normalized = _normalize_schedule(payload)
        _set_schedule_cache(normalized)
        return dict(normalized)
    except Exception as exc:
        logger.warning("Failed to fetch auto restart schedule: %s", exc)
        _set_schedule_cache(default)
        return dict(default)


async def get_auto_restart_status(force_refresh: bool = False) -> Dict[str, Any]:
    if (
        not force_refresh
        and _cached_status is not None
        and _is_fresh(_cached_status_at, AUTO_RESTART_STATUS_CACHE_TTL_SECONDS)
    ):
        return dict(_cached_status)

    schedule = await get_auto_restart_schedule(force_refresh=force_refresh)
    default = _build_status_from_schedule(schedule)
    try:
        redis = await get_redis()
        payload = _decode_payload(await redis.get(AUTO_RESTART_STATUS_KEY))
        if not payload:
            _set_status_cache(default)
            return dict(default)

        normalized = {
            **default,
            "state": str(payload.get("state") or default["state"]),
            "summary": str(payload.get("summary") or default["summary"]),
            "last_triggered_at": payload.get("last_triggered_at"),
            "last_result_at": payload.get("last_result_at"),
            "last_error": payload.get("last_error"),
            "last_result": payload.get("last_result")
            if isinstance(payload.get("last_result"), dict)
            else None,
        }
        normalized = _upsert_status_context(normalized, schedule, _now_utc())
        _set_status_cache(normalized)
        return dict(normalized)
    except Exception as exc:
        logger.warning("Failed to fetch auto restart status: %s", exc)
        _set_status_cache(default)
        return dict(default)


def _append_scheduled_runs(
    schedule: Dict[str, Any],
    scheduled_runs_wib: List[str],
    *,
    reason: Optional[str],
) -> int:
    if not scheduled_runs_wib:
        return 0

    now_utc = _now_utc()
    entries = _normalize_entries(schedule.get("entries"))
    pending_utc = {
        str(entry.get("scheduled_at_utc"))
        for entry in entries
        if str(entry.get("status")).lower() == "pending"
    }
    added_count = 0
    for raw in scheduled_runs_wib:
        parsed_wib = _parse_wib_datetime(str(raw))
        parsed_utc = parsed_wib.astimezone(timezone.utc)
        if parsed_utc <= now_utc:
            raise HTTPException(
                status_code=400,
                detail=f"Jadwal {raw} sudah lewat. Pilih waktu WIB di masa depan.",
            )
        utc_iso = parsed_utc.isoformat()
        if utc_iso in pending_utc:
            continue
        entries.append(
            {
                "id": _entry_id(),
                "scheduled_at_wib": parsed_wib.isoformat(),
                "scheduled_at_utc": utc_iso,
                "status": "pending",
                "created_at": _now_iso(),
                "triggered_at": None,
                "finished_at": None,
                "error": None,
                "reason": reason,
            }
        )
        pending_utc.add(utc_iso)
        added_count += 1

    entries.sort(key=lambda item: str(item.get("scheduled_at_utc") or ""))
    schedule["entries"] = entries[-AUTO_RESTART_MAX_ENTRIES:]
    return added_count


async def set_auto_restart_schedule(
    *,
    enabled: bool,
    time_wib: str,
    restart_buffer_minutes: int = 30,
    full_restart: bool = True,
    include_data_services: bool = True,
    restart_timeout_seconds: int = 300,
    reason: Optional[str] = None,
    source: str = "manual",
    actor: Optional[str] = None,
    scheduled_runs_wib: Optional[List[str]] = None,
    replace_runs: bool = False,
) -> Dict[str, Any]:
    existing = await get_auto_restart_schedule(force_refresh=True)
    schedule = _normalize_schedule(existing)

    schedule.update(
        {
            "enabled": bool(enabled),
            "timezone": "Asia/Jakarta",
            "time_wib": _normalize_time_wib(time_wib),
            "restart_buffer_minutes": max(5, min(int(restart_buffer_minutes or 30), 180)),
            "full_restart": bool(full_restart),
            "include_data_services": bool(include_data_services),
            "restart_timeout_seconds": max(60, min(int(restart_timeout_seconds or 300), 1200)),
            "reason": (
                str(reason).strip()
                if isinstance(reason, str) and reason.strip()
                else "Auto restart terjadwal WIB"
            ),
            "source": source,
            "actor": actor,
            "updated_at": _now_iso(),
        }
    )

    entries = _normalize_entries(schedule.get("entries"))
    if replace_runs:
        entries = [entry for entry in entries if str(entry.get("status")).lower() != "pending"]
    schedule["entries"] = entries

    added_count = 0
    if scheduled_runs_wib:
        added_count = _append_scheduled_runs(
            schedule,
            [str(item).strip() for item in scheduled_runs_wib if str(item).strip()],
            reason=schedule.get("reason"),
        )

    await _persist_schedule(schedule)

    status = _build_status_from_schedule(schedule)
    status["summary"] = (
        f"Jadwal auto restart diperbarui. Tambahan jadwal: {added_count}."
        if added_count > 0
        else status["summary"]
    )
    await _persist_status(status)

    logger.warning(
        "Auto restart schedule updated enabled=%s actor=%s source=%s added=%s pending=%s",
        schedule["enabled"],
        actor,
        source,
        added_count,
        status.get("pending_count"),
    )
    return dict(schedule)


async def _acquire_exec_lock(lock_seconds: int = 180) -> Optional[str]:
    token = f"{os.getpid()}-{time.time_ns()}"
    try:
        redis = await get_redis()
        acquired = await redis.set(AUTO_RESTART_EXEC_LOCK_KEY, token, nx=True, ex=lock_seconds)
        if acquired:
            return token
    except Exception as exc:
        logger.warning("Failed to acquire auto restart exec lock: %s", exc)
    return None


async def _release_exec_lock(token: Optional[str]) -> None:
    if not token:
        return
    try:
        redis = await get_redis()
        current = await redis.get(AUTO_RESTART_EXEC_LOCK_KEY)
        if isinstance(current, bytes):
            current = current.decode("utf-8", errors="ignore")
        if current == token:
            await redis.delete(AUTO_RESTART_EXEC_LOCK_KEY)
    except Exception as exc:
        logger.warning("Failed to release auto restart exec lock: %s", exc)


def _get_due_entry(schedule: Dict[str, Any], now_utc: datetime) -> Optional[Dict[str, Any]]:
    entries = _normalize_entries(schedule.get("entries"))
    due_candidates: List[Dict[str, Any]] = []
    for entry in entries:
        if str(entry.get("status")).lower() != "pending":
            continue
        scheduled_at_utc = _entry_utc(entry)
        if scheduled_at_utc and scheduled_at_utc <= now_utc:
            due_candidates.append(entry)
    if not due_candidates:
        return None
    due_candidates.sort(key=lambda item: str(item.get("scheduled_at_utc") or ""))
    return due_candidates[0]


def _update_entry_state(
    schedule: Dict[str, Any],
    entry_id: str,
    *,
    state: str,
    error: Optional[str] = None,
    set_triggered: bool = False,
    set_finished: bool = False,
) -> None:
    entries = _normalize_entries(schedule.get("entries"))
    for entry in entries:
        if str(entry.get("id")) != str(entry_id):
            continue
        entry["status"] = state
        if set_triggered:
            entry["triggered_at"] = _now_iso()
        if set_finished:
            entry["finished_at"] = _now_iso()
        entry["error"] = error
        break
    schedule["entries"] = entries


async def run_auto_restart_scheduler_tick(
    *,
    force: bool = False,
    dry_run: bool = False,
    reason: Optional[str] = None,
    source: str = "auto_scheduler",
    actor: str = "auto_restart_scheduler",
) -> Dict[str, Any]:
    now_utc = _now_utc()
    schedule = await get_auto_restart_schedule(force_refresh=True)
    schedule = _normalize_schedule(schedule)
    enabled = bool(schedule.get("enabled", False))

    due_entry = _get_due_entry(schedule, now_utc)
    should_run = bool(force or due_entry)
    status = _upsert_status_context(await get_auto_restart_status(force_refresh=True), schedule, now_utc)

    if not enabled and not force:
        status.update({"state": "disabled", "summary": "Auto restart terjadwal dinonaktifkan.", "last_error": None})
        await _persist_status(status)
        return dict(status)

    if not should_run:
        status.update(
            {
                "state": "scheduled" if int(status.get("pending_count") or 0) > 0 else "idle",
                "summary": _build_status_from_schedule(schedule, now_utc=now_utc).get("summary"),
                "last_error": None,
            }
        )
        await _persist_status(status)
        return dict(status)

    lock_token = await _acquire_exec_lock()
    if not lock_token:
        status.update(
            {
                "state": "running",
                "summary": "Auto restart sedang diproses oleh worker lain.",
            }
        )
        await _persist_status(status)
        return dict(status)

    status.update(
        {
            "state": "running",
            "summary": "Menjalankan evaluasi restart terjadwal...",
            "last_triggered_at": _now_iso(),
            "last_error": None,
        }
    )
    if due_entry and not dry_run:
        _update_entry_state(
            schedule,
            due_entry["id"],
            state="running",
            set_triggered=True,
        )
        await _persist_schedule(schedule)
    await _persist_status(status)

    run_result: Dict[str, Any]
    try:
        from app.api.monitoring import RestartSystemRequest, restart_system_safely
        from app.database import async_session_write

        payload = RestartSystemRequest(
            reason=reason
            or schedule.get("reason")
            or (
                f"Auto restart jadwal {due_entry.get('scheduled_at_wib')}"
                if due_entry
                else "Auto restart manual scheduler run"
            ),
            restart_buffer_minutes=int(schedule.get("restart_buffer_minutes") or 30),
            full_restart=bool(schedule.get("full_restart", True)),
            include_data_services=bool(schedule.get("include_data_services", True)),
            restart_timeout_seconds=int(schedule.get("restart_timeout_seconds") or 300),
            dry_run=bool(dry_run),
        )
        actor_obj = SimpleNamespace(username=actor)
        async with async_session_write() as db:
            run_result = await restart_system_safely(
                payload=payload,
                current_user=actor_obj,
                db=db,
            )

        if due_entry and not dry_run:
            _update_entry_state(
                schedule,
                due_entry["id"],
                state="success",
                set_finished=True,
            )
            await _persist_schedule(schedule)

        status = _upsert_status_context(status, schedule, _now_utc())
        status.update(
            {
                "state": "success",
                "summary": (
                    "Dry-run restart terjadwal berhasil diverifikasi."
                    if dry_run
                    else "Restart terjadwal berhasil dijalankan."
                ),
                "last_result_at": _now_iso(),
                "last_error": None,
                "last_result": run_result if isinstance(run_result, dict) else None,
            }
        )
        await _persist_status(status)
        return dict(status)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        state = "blocked" if int(exc.status_code) == 409 else "failed"
        message = str(detail.get("message") or "Eksekusi restart terjadwal gagal.")

        if due_entry and not dry_run:
            _update_entry_state(
                schedule,
                due_entry["id"],
                state=state,
                error=message,
                set_finished=True,
            )
            await _persist_schedule(schedule)

        status = _upsert_status_context(status, schedule, _now_utc())
        status.update(
            {
                "state": state,
                "summary": message,
                "last_result_at": _now_iso(),
                "last_error": message,
                "last_result": {"status_code": exc.status_code, "detail": detail},
            }
        )
        await _persist_status(status)
        return dict(status)
    except Exception as exc:
        message = str(exc)
        if due_entry and not dry_run:
            _update_entry_state(
                schedule,
                due_entry["id"],
                state="failed",
                error=message,
                set_finished=True,
            )
            await _persist_schedule(schedule)

        status = _upsert_status_context(status, schedule, _now_utc())
        status.update(
            {
                "state": "failed",
                "summary": f"Eksekusi restart terjadwal gagal: {message}",
                "last_result_at": _now_iso(),
                "last_error": message,
                "last_result": {"error": message},
            }
        )
        await _persist_status(status)
        return dict(status)
    finally:
        await _release_exec_lock(lock_token)
