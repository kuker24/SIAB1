"""Async violation event queue/cache service for mobile-first exam runtime.

Hot requests should validate lightly, enqueue to Redis, update aggregate runtime
cache, and return quickly. A background drainer batch-writes PostgreSQL and
broadcasts aggregate/high-severity updates for the admin dashboard.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exam_session_helpers import safe_int
from app.core.monitoring_delta import publish_monitoring_delta
from app.core.redis_pubsub import get_redis, get_session_data, publish_message, store_session_data
from app.core.violation_metadata import (
    canonical_violation_event_type,
    get_violation_metadata,
    get_violation_warning_message,
    strip_violation_prefix,
)
from app.core.violation_scoring import (
    is_violation_event_disabled,
    should_count_violation_for_score,
)
from app.database import async_session_write
from app.models.session import ExamLog, ExamSession
from app.schemas.answer import ViolationLog, ViolationResponse

logger = logging.getLogger(__name__)

PENDING_KEY = "runtime:violation:pending"
DEADLETTER_KEY = "runtime:violation:deadletter"
AGGREGATE_KEY_TEMPLATE = "runtime:violation:aggregate:{exam_id}"
SESSION_KEY_TEMPLATE = "runtime:violation:session:{session_id}"
SESSION_EVENTS_KEY_TEMPLATE = "runtime:violation:session:{session_id}:events"
DEDUPE_KEY_TEMPLATE = "runtime:violation:session:{session_id}:dedupe:{fingerprint}"
WORKER_LOCK_KEY = "runtime:violation:worker:lock"

ACTIVE_SESSION_STATUSES = ("in_progress", "active", "paused")
TERMINAL_SESSION_STATUSES = {"submitted", "completed", "abandoned", "terminated", "kicked"}
CACHE_TTL_SECONDS = 3 * 60 * 60
DEDUPE_TTL_SECONDS = 12
SESSION_EVENT_LIMIT = 50
DEFAULT_DRAIN_BATCH_SIZE = 100
DEFAULT_DRAIN_INTERVAL_SECONDS = 2.0
DEFAULT_WORKER_LOCK_SECONDS = 10


@dataclass(frozen=True)
class ViolationEnqueueResult:
    """Result returned from the hot violation enqueue path."""

    status: str
    violation_count: int
    warning: Optional[str] = None

    def to_response(self) -> ViolationResponse:
        return ViolationResponse(
            status=self.status,
            violation_count=max(0, int(self.violation_count or 0)),
            warning=self.warning,
        )


def _ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _severity_rank(severity: str) -> int:
    ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    return ranks.get(str(severity or "").lower(), 1)


def _risk_status(total_count: int, severity: str) -> str:
    severity_value = str(severity or "").lower()
    if severity_value in {"high", "critical"} or total_count >= 5:
        return "high-risk"
    if total_count >= 2 or severity_value in {"medium"}:
        return "suspicious"
    return "normal"


def _parse_optional_datetime(raw_value: Any) -> Optional[datetime]:
    if not raw_value:
        return None
    if isinstance(raw_value, datetime):
        value = raw_value
    else:
        raw = str(raw_value).strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            value = datetime.fromisoformat(raw)
        except Exception:
            return None
    return _ensure_aware_utc(value)


def _fingerprint_event(session_id: int, event_type: str, payload: Dict[str, Any]) -> str:
    payload_subset = {
        "event_type": event_type,
        "source": payload.get("source"),
        "violation_type": payload.get("violation_type"),
        "reason": payload.get("reason"),
        "details": payload.get("details"),
    }
    digest_source = f"{session_id}:{_json_dumps(payload_subset)[:1500]}"
    return hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:24]


async def _publish_exam_monitor_event(exam_id: int, payload: Dict[str, Any]) -> None:
    await publish_message(f"exam_monitor_{exam_id}", payload)
    try:
        await publish_monitoring_delta(
            exam_id=exam_id,
            event_type=str(payload.get("type") or "event"),
            payload=payload,
        )
    except Exception as delta_exc:
        logger.debug("Failed to mirror violation event to delta stream: %s", str(delta_exc))


async def _read_cached_session_state(
    *,
    session_id: int,
    current_user_id: int,
) -> Optional[Dict[str, Any]]:
    try:
        cached = await get_session_data(session_id)
    except Exception:
        logger.debug("Violation session cache read failed", exc_info=True)
        return None

    if not cached:
        return None

    cached_session_id = safe_int(cached.get("session_id"))
    if cached_session_id is not None and cached_session_id != session_id:
        return None
    if cached_session_id is None:
        return None

    cached_user_id = safe_int(cached.get("user_id"))
    if cached_user_id != current_user_id:
        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

    cached_exam_id = safe_int(cached.get("exam_id"))
    status = str(cached.get("status") or "").strip().lower()
    if not cached_exam_id or not status:
        return None

    return {
        "id": session_id,
        "exam_id": cached_exam_id,
        "violation_count": safe_int(cached.get("violation_count")) or 0,
        "status": status,
        "end_time": _parse_optional_datetime(cached.get("end_time")),
        "source": "cache",
    }


async def _refresh_session_runtime_cache(
    *,
    session_id: int,
    user_id: int,
    session_state: Dict[str, Any],
) -> None:
    try:
        cached = await get_session_data(session_id) or {}
        if cached and safe_int(cached.get("user_id")) not in {None, user_id}:
            return
        end_time = session_state.get("end_time")
        cached.update(
            {
                "session_id": session_id,
                "user_id": user_id,
                "exam_id": int(session_state["exam_id"]),
                "status": str(session_state.get("status") or ""),
                "end_time": end_time.isoformat() if isinstance(end_time, datetime) else end_time,
                "violation_count": int(session_state.get("violation_count") or 0),
            }
        )
        await store_session_data(session_id, cached)
    except Exception:
        logger.debug("Violation session cache refresh failed", exc_info=True)


async def _load_session_state_from_db(
    db: AsyncSession,
    *,
    session_id: int,
    current_user_id: int,
) -> Optional[Dict[str, Any]]:
    session_state_result = await db.execute(
        select(
            ExamSession.id,
            ExamSession.exam_id,
            ExamSession.violation_count,
            ExamSession.status,
            ExamSession.end_time,
        ).where(
            ExamSession.id == session_id,
            ExamSession.user_id == current_user_id,
        )
    )
    row = session_state_result.mappings().one_or_none()
    if not row:
        return None
    state = dict(row)
    state["status"] = str(state.get("status") or "").strip().lower()
    state["source"] = "db"
    await _refresh_session_runtime_cache(
        session_id=session_id,
        user_id=current_user_id,
        session_state=state,
    )
    return state


async def _resolve_session_state_for_enqueue(
    db: AsyncSession,
    *,
    violation_data: ViolationLog,
    current_user: Any,
) -> Optional[Dict[str, Any]]:
    session_id = int(violation_data.session_id)
    current_user_id = int(current_user.id)

    cached_state = await _read_cached_session_state(
        session_id=session_id,
        current_user_id=current_user_id,
    )
    if cached_state is not None:
        return cached_state

    return await _load_session_state_from_db(
        db,
        session_id=session_id,
        current_user_id=current_user_id,
    )


async def _cache_enqueued_event(event: Dict[str, Any], violation_meta: Dict[str, Any]) -> int:
    """Update Redis aggregate/session runtime cache and return session event count."""
    redis = await get_redis()
    session_id = int(event["session_id"])
    exam_id = int(event["exam_id"])
    aggregate_key = AGGREGATE_KEY_TEMPLATE.format(exam_id=exam_id)
    session_key = SESSION_KEY_TEMPLATE.format(session_id=session_id)
    session_events_key = SESSION_EVENTS_KEY_TEMPLATE.format(session_id=session_id)
    reported_at = str(event["reported_at"])
    severity = str(violation_meta.get("severity") or "low")

    session_total = int(await redis.hincrby(session_key, "violation_count", 1))
    await redis.hset(
        session_key,
        mapping={
            "exam_id": exam_id,
            "session_id": session_id,
            "user_id": int(event["user_id"]),
            "username": str(event.get("username") or ""),
            "last_violation_type": str(event["event_type"]),
            "last_violation_time": reported_at,
            "last_violation_label": str(violation_meta.get("label") or event["event_type"]),
            "last_violation_severity": severity,
            "risk_score": max(session_total, _severity_rank(severity) * 2),
            "status": _risk_status(session_total, severity),
        },
    )
    await redis.expire(session_key, CACHE_TTL_SECONDS)

    await redis.hincrby(aggregate_key, "total_events", 1)
    await redis.hincrby(aggregate_key, f"event_type:{event['event_type']}", 1)
    await redis.hincrby(aggregate_key, f"severity:{severity}", 1)
    await redis.hset(
        aggregate_key,
        mapping={
            f"session:{session_id}:count": session_total,
            f"session:{session_id}:last_type": str(event["event_type"]),
            f"session:{session_id}:last_time": reported_at,
            f"session:{session_id}:status": _risk_status(session_total, severity),
        },
    )
    await redis.expire(aggregate_key, CACHE_TTL_SECONDS)

    detail_event = {
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "raw_event_type": event.get("raw_event_type"),
        "label": violation_meta.get("label"),
        "severity": severity,
        "category": violation_meta.get("category"),
        "reported_at": reported_at,
        "queued_at": event.get("queued_at"),
    }
    await redis.lpush(session_events_key, _json_dumps(detail_event))
    await redis.ltrim(session_events_key, 0, SESSION_EVENT_LIMIT - 1)
    await redis.expire(session_events_key, CACHE_TTL_SECONDS)
    return session_total


async def enqueue_violation_event(
    db: AsyncSession,
    violation_data: ViolationLog,
    current_user: Any,
) -> ViolationEnqueueResult:
    """Validate lightly and enqueue a violation event without direct DB writes."""
    violation_payload = dict(violation_data.event_data or {})
    reported_at = _ensure_aware_utc(violation_data.timestamp or datetime.now(timezone.utc))
    normalized_event_type = canonical_violation_event_type(
        violation_data.event_type,
        violation_payload,
        assume_violation=True,
    )
    if not normalized_event_type:
        raise HTTPException(status_code=400, detail="Jenis pelanggaran tidak valid")

    try:
        session_state = await _resolve_session_state_for_enqueue(
            db,
            violation_data=violation_data,
            current_user=current_user,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "Violation session validation fallback failed; dropping best-effort event: %s",
            str(exc),
        )
        return ViolationEnqueueResult(status="dropped", violation_count=0)

    if not session_state:
        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

    current_count = int(session_state["violation_count"] or 0)
    if is_violation_event_disabled(normalized_event_type):
        return ViolationEnqueueResult(status="ignored", violation_count=current_count)

    session_status = str(session_state["status"] or "")
    if session_status in TERMINAL_SESSION_STATUSES:
        return ViolationEnqueueResult(status="ignored", violation_count=current_count)

    session_end_time = session_state["end_time"]
    if session_end_time is not None:
        session_end_time = _ensure_aware_utc(session_end_time)
        if reported_at >= (session_end_time - timedelta(seconds=5)):
            return ViolationEnqueueResult(status="ignored", violation_count=current_count)

    violation_meta = get_violation_metadata(
        normalized_event_type,
        violation_payload,
        assume_violation=True,
    )
    effective_exam_id = (
        violation_data.exam_id
        if violation_data.exam_id and violation_data.exam_id > 0
        else int(session_state["exam_id"])
    )
    event = {
        "event_id": uuid.uuid4().hex,
        "session_id": int(session_state["id"]),
        "exam_id": int(effective_exam_id),
        "user_id": int(current_user.id),
        "username": str(getattr(current_user, "username", "") or ""),
        "event_type": normalized_event_type,
        "raw_event_type": violation_data.event_type,
        "event_data": violation_payload,
        "reported_at": reported_at.isoformat(),
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "user_agent": violation_data.user_agent,
        "screen_resolution": violation_data.screen_resolution,
        "session_status": session_status,
    }

    try:
        redis = await get_redis()
        fingerprint = _fingerprint_event(int(session_state["id"]), normalized_event_type, violation_payload)
        dedupe_key = DEDUPE_KEY_TEMPLATE.format(session_id=int(session_state["id"]), fingerprint=fingerprint)
        is_new = await redis.set(dedupe_key, event["event_id"], nx=True, ex=DEDUPE_TTL_SECONDS)
        if not is_new:
            return ViolationEnqueueResult(
                status="duplicate",
                violation_count=current_count,
                warning=get_violation_warning_message(current_count),
            )

        await redis.rpush(PENDING_KEY, _json_dumps(event))
        await redis.expire(PENDING_KEY, CACHE_TTL_SECONDS)
        cached_count = await _cache_enqueued_event(event, violation_meta)
        await _refresh_session_runtime_cache(
            session_id=int(session_state["id"]),
            user_id=int(current_user.id),
            session_state={
                **dict(session_state),
                "violation_count": max(current_count, cached_count),
            },
        )
    except Exception:
        # Best-effort by design: violation logging must not block answers/final submit.
        logger.exception("Failed to enqueue violation event; dropping best-effort event")
        try:
            await redis.lpush(DEADLETTER_KEY, _json_dumps({"reason": "enqueue_failed", **event}))
            await redis.ltrim(DEADLETTER_KEY, 0, 999)
            await redis.expire(DEADLETTER_KEY, CACHE_TTL_SECONDS)
        except Exception:
            logger.debug("Failed to write violation deadletter", exc_info=True)
        return ViolationEnqueueResult(
            status="dropped",
            violation_count=current_count,
            warning=get_violation_warning_message(current_count),
        )

    return ViolationEnqueueResult(
        status="queued",
        violation_count=max(current_count, cached_count),
        warning=get_violation_warning_message(max(current_count, cached_count)),
    )


async def _pop_pending_batch(batch_size: int) -> list[Dict[str, Any]]:
    redis = await get_redis()
    events: list[Dict[str, Any]] = []
    for _ in range(max(1, batch_size)):
        raw = await redis.lpop(PENDING_KEY)
        if not raw:
            break
        try:
            events.append(json.loads(raw))
        except Exception:
            logger.warning("Invalid violation event JSON skipped")
    return events


async def _write_deadletter(event: Dict[str, Any], reason: str) -> None:
    try:
        redis = await get_redis()
        await redis.lpush(DEADLETTER_KEY, _json_dumps({"reason": reason, "event": event}))
        await redis.ltrim(DEADLETTER_KEY, 0, 999)
        await redis.expire(DEADLETTER_KEY, CACHE_TTL_SECONDS)
    except Exception:
        logger.debug("Failed to write violation deadletter", exc_info=True)


async def _process_event(db: AsyncSession, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    session_id = int(event["session_id"])
    user_id = int(event["user_id"])
    normalized_event_type = str(event["event_type"])
    violation_payload = dict(event.get("event_data") or {})
    reported_at = _ensure_aware_utc(datetime.fromisoformat(str(event["reported_at"])))

    session_state_result = await db.execute(
        select(
            ExamSession.id,
            ExamSession.exam_id,
            ExamSession.violation_count,
            ExamSession.status,
            ExamSession.end_time,
        ).where(
            ExamSession.id == session_id,
            ExamSession.user_id == user_id,
        )
    )
    session_state = session_state_result.mappings().one_or_none()
    if not session_state:
        await _write_deadletter(event, "session_not_found")
        return None

    session_status = str(session_state["status"] or "")
    if session_status in TERMINAL_SESSION_STATUSES:
        return None

    session_end_time = session_state["end_time"]
    if session_end_time is not None:
        session_end_time = _ensure_aware_utc(session_end_time)
        if reported_at >= (session_end_time - timedelta(seconds=5)):
            return None

    should_count_for_score, counting_policy = await should_count_violation_for_score(
        db,
        session_id=session_id,
        normalized_event_type=normalized_event_type,
        violation_payload=violation_payload,
        reported_at=reported_at,
    )
    increment_value = 1 if should_count_for_score else 0

    session_update = await db.execute(
        update(ExamSession)
        .where(
            ExamSession.id == session_id,
            ExamSession.user_id == user_id,
            ExamSession.status.in_(ACTIVE_SESSION_STATUSES),
        )
        .values(violation_count=func.coalesce(ExamSession.violation_count, 0) + increment_value)
        .returning(ExamSession.id, ExamSession.exam_id, ExamSession.violation_count)
    )
    session_row = session_update.mappings().one_or_none()
    if not session_row:
        return None

    violation_meta = get_violation_metadata(
        normalized_event_type,
        violation_payload,
        assume_violation=True,
    )
    db.add(
        ExamLog(
            session_id=session_id,
            event_type=normalized_event_type,
            event_data={
                **violation_payload,
                "label": violation_meta["label"],
                "severity": violation_meta["severity"],
                "category": violation_meta["category"],
                "description": violation_meta["description"],
                "raw_event_type": event.get("raw_event_type"),
                "source": violation_payload.get("source", "web"),
                "counted_for_score": should_count_for_score,
                "counting_policy": counting_policy,
                "reported_at": reported_at.isoformat(),
                "queued_at": event.get("queued_at"),
                "processed_async": True,
                "user_agent": event.get("user_agent"),
                "screen_resolution": event.get("screen_resolution"),
            },
        )
    )
    violation_count = int(session_row["violation_count"] or 0)
    return {
        "exam_id": int(session_row["exam_id"]),
        "user_id": user_id,
        "username": str(event.get("username") or ""),
        "session_id": session_id,
        "event_type": normalized_event_type,
        "violation_type": strip_violation_prefix(normalized_event_type),
        "violation_label": violation_meta["label"],
        "violation_severity": violation_meta["severity"],
        "violation_category": violation_meta["category"],
        "counted_for_score": should_count_for_score,
        "counting_policy": counting_policy,
        "violation_count": violation_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_status": session_status,
    }


async def drain_violation_events_once(batch_size: int = DEFAULT_DRAIN_BATCH_SIZE) -> int:
    """Drain one Redis batch into PostgreSQL. Returns processed/broadcast count."""
    redis = await get_redis()
    lock_value = datetime.now(timezone.utc).isoformat()
    lock_acquired = await redis.set(
        WORKER_LOCK_KEY,
        lock_value,
        nx=True,
        ex=DEFAULT_WORKER_LOCK_SECONDS,
    )
    if not lock_acquired:
        return 0

    try:
        events = await _pop_pending_batch(batch_size)
        if not events:
            return 0

        broadcasts: list[Dict[str, Any]] = []
        try:
            async with async_session_write() as db:
                for event in events:
                    try:
                        payload = await _process_event(db, event)
                        if payload:
                            broadcasts.append(payload)
                    except Exception:
                        logger.exception("Failed processing violation event")
                        await _write_deadletter(event, "process_failed")
                await db.commit()
        except Exception:
            logger.exception("Violation event batch failed")
            for event in events:
                await _write_deadletter(event, "batch_failed")
            return 0

        for payload in broadcasts:
            try:
                session_id = int(payload["session_id"])
                cached_session_data = await get_session_data(session_id)
                if cached_session_data and safe_int(cached_session_data.get("user_id")) == int(payload["user_id"]):
                    cached_session_data["violation_count"] = int(payload["violation_count"] or 0)
                    cached_session_data["status"] = payload.get("session_status") or "in_progress"
                    await store_session_data(session_id, cached_session_data)
            except Exception:
                logger.debug("Failed to refresh cached session violation count", exc_info=True)

            try:
                await _publish_exam_monitor_event(
                    int(payload["exam_id"]),
                    {"type": "violation_detected", **payload},
                )
            except Exception:
                logger.exception(
                    "Async violation broadcast failed exam_id=%s session_id=%s event_type=%s",
                    payload.get("exam_id"),
                    payload.get("session_id"),
                    payload.get("event_type"),
                )

        return len(broadcasts)
    finally:
        try:
            current_lock = await redis.get(WORKER_LOCK_KEY)
            if current_lock == lock_value:
                await redis.delete(WORKER_LOCK_KEY)
        except Exception:
            logger.debug("Failed to release violation worker lock", exc_info=True)


async def violation_event_drain_loop(stop_event: asyncio.Event) -> None:
    """Background loop for async violation batch writes."""
    logger.info("Violation event drain loop started")
    while not stop_event.is_set():
        try:
            if not settings.violation_async_enabled:
                await asyncio.wait_for(stop_event.wait(), timeout=DEFAULT_DRAIN_INTERVAL_SECONDS)
                continue
            await drain_violation_events_once()
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Violation event drain loop tick failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=DEFAULT_DRAIN_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
    logger.info("Violation event drain loop stopped")
