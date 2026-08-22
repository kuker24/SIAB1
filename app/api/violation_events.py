"""Student violation event routes.

Violation detection remains enabled, but the default production path is async so
it does not block answer/final-submit hot paths.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exam_monitor_events import publish_exam_monitor_event
from app.core.exam_session_helpers import safe_int
from app.core.redis_pubsub import get_session_data, store_session_data
from app.core.runtime_policy import (
    get_mobile_runtime_policy,
    is_violation_disabled_by_mobile_policy,
)
from app.core.security import AuthenticatedUser, get_current_user_hot_path
from app.core.violation_metadata import (
    canonical_violation_event_type,
    get_violation_metadata,
    get_violation_warning_message,
    strip_violation_prefix,
)
from app.core.violation_scoring import is_violation_event_disabled, should_count_violation_for_score
from app.database import get_db
from app.models.session import ExamLog, ExamSession
from app.schemas.answer import ViolationLog, ViolationResponse
from app.services.violation_event_service import enqueue_violation_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exams", tags=["Violation Events"])


def _ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ignored_violation_response(violation_count: int) -> ViolationResponse:
    return ViolationResponse(
        status="ignored",
        violation_count=max(0, int(violation_count or 0)),
        warning=None,
    )


@router.post("/log-violation", response_model=ViolationResponse, status_code=status.HTTP_202_ACCEPTED)
async def log_violation(
    violation_data: ViolationLog,
    current_user: AuthenticatedUser = Depends(get_current_user_hot_path),
    db: AsyncSession = Depends(get_db),
):
    """Log a cheating violation without blocking answer hot paths."""
    violation_payload = dict(violation_data.event_data or {})
    reported_at = _ensure_aware_utc(violation_data.timestamp or datetime.now(timezone.utc))
    normalized_event_type = canonical_violation_event_type(
        violation_data.event_type,
        violation_payload,
        assume_violation=True,
    )
    if not normalized_event_type:
        raise HTTPException(status_code=400, detail="Jenis pelanggaran tidak valid")

    runtime_policy = await get_mobile_runtime_policy(force_refresh=False)
    if is_violation_disabled_by_mobile_policy(normalized_event_type, runtime_policy):
        logger.info(
            "Ignored non-critical violation by runtime policy session_id=%s event_type=%s mode=%s",
            violation_data.session_id,
            normalized_event_type,
            runtime_policy.get("mode"),
        )
        return _ignored_violation_response(0)

    if settings.violation_async_enabled:
        enqueue_result = await enqueue_violation_event(db, violation_data, current_user)
        return enqueue_result.to_response()

    active_session_statuses = ("in_progress", "active", "paused")
    terminal_session_statuses = {"submitted", "completed", "abandoned", "terminated", "kicked"}

    session_state_result = await db.execute(
        select(
            ExamSession.id,
            ExamSession.exam_id,
            ExamSession.violation_count,
            ExamSession.status,
            ExamSession.end_time,
        ).where(
            ExamSession.id == violation_data.session_id,
            ExamSession.user_id == current_user.id,
        )
    )
    session_state = session_state_result.mappings().one_or_none()

    if not session_state:
        raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

    if is_violation_event_disabled(normalized_event_type):
        logger.info(
            "Ignored disabled violation event session_id=%s event_type=%s",
            violation_data.session_id,
            normalized_event_type,
        )
        return _ignored_violation_response(session_state["violation_count"])

    session_status = str(session_state["status"] or "")
    if session_status in terminal_session_statuses:
        logger.info(
            "Ignored violation for closed session session_id=%s status=%s event_type=%s",
            violation_data.session_id,
            session_status,
            normalized_event_type,
        )
        return _ignored_violation_response(session_state["violation_count"])

    session_end_time = session_state["end_time"]
    if session_end_time is not None:
        if session_end_time.tzinfo is None:
            session_end_time = session_end_time.replace(tzinfo=timezone.utc)
        if reported_at >= (session_end_time - timedelta(seconds=5)):
            logger.info(
                "Ignored late violation near submit session_id=%s status=%s event_type=%s",
                violation_data.session_id,
                session_status,
                normalized_event_type,
            )
            return _ignored_violation_response(session_state["violation_count"])

    should_count_for_score, counting_policy = await should_count_violation_for_score(
        db,
        session_id=int(session_state["id"]),
        normalized_event_type=normalized_event_type,
        violation_payload=violation_payload,
        reported_at=reported_at,
    )
    increment_value = 1 if should_count_for_score else 0

    session_update = await db.execute(
        update(ExamSession)
        .where(
            ExamSession.id == violation_data.session_id,
            ExamSession.user_id == current_user.id,
            ExamSession.status.in_(active_session_statuses),
        )
        .values(
            violation_count=func.coalesce(ExamSession.violation_count, 0) + increment_value
        )
        .returning(
            ExamSession.id,
            ExamSession.exam_id,
            ExamSession.violation_count,
        )
    )
    session_row = session_update.mappings().one_or_none()

    if not session_row:
        latest_state_result = await db.execute(
            select(ExamSession.violation_count, ExamSession.status).where(
                ExamSession.id == violation_data.session_id,
                ExamSession.user_id == current_user.id,
            )
        )
        latest_state = latest_state_result.mappings().one_or_none()

        if not latest_state:
            raise HTTPException(status_code=404, detail="Sesi ujian tidak ditemukan")

        logger.info(
            "Ignored violation after session state transition session_id=%s status=%s event_type=%s",
            violation_data.session_id,
            str(latest_state["status"] or ""),
            normalized_event_type,
        )
        return _ignored_violation_response(latest_state["violation_count"])

    if not should_count_for_score:
        logger.info(
            "Violation logged as warning-only session_id=%s event_type=%s policy=%s",
            violation_data.session_id,
            normalized_event_type,
            counting_policy,
        )

    effective_exam_id = (
        violation_data.exam_id
        if violation_data.exam_id and violation_data.exam_id > 0
        else int(session_row["exam_id"])
    )

    violation_meta = get_violation_metadata(
        normalized_event_type,
        violation_payload,
        assume_violation=True,
    )

    log = ExamLog(
        session_id=int(session_row["id"]),
        event_type=normalized_event_type,
        event_data={
            **violation_payload,
            "label": violation_meta["label"],
            "severity": violation_meta["severity"],
            "category": violation_meta["category"],
            "description": violation_meta["description"],
            "raw_event_type": violation_data.event_type,
            "source": violation_payload.get("source", "web"),
            "counted_for_score": should_count_for_score,
            "counting_policy": counting_policy,
            "reported_at": reported_at.isoformat(),
            "user_agent": violation_data.user_agent,
            "screen_resolution": violation_data.screen_resolution,
        },
    )
    db.add(log)
    await db.commit()
    try:
        cached_session_data = await get_session_data(int(session_row["id"]))
        if cached_session_data and safe_int(cached_session_data.get("user_id")) == current_user.id:
            cached_session_data["violation_count"] = int(session_row["violation_count"] or 0)
            cached_session_data["status"] = session_status or "in_progress"
            await store_session_data(int(session_row["id"]), cached_session_data)
    except Exception as cache_exc:
        logger.debug(
            "LOG-VIOLATION | session=%s | failed to refresh runtime snapshot: %s",
            int(session_row["id"]),
            str(cache_exc),
        )

    event_timestamp = datetime.now(timezone.utc).isoformat()
    broadcast_payload = {
        "type": "violation_detected",
        "exam_id": effective_exam_id,
        "user_id": current_user.id,
        "username": current_user.username,
        "session_id": int(session_row["id"]),
        "event_type": normalized_event_type,
        "violation_type": strip_violation_prefix(normalized_event_type),
        "violation_label": violation_meta["label"],
        "violation_severity": violation_meta["severity"],
        "violation_category": violation_meta["category"],
        "counted_for_score": should_count_for_score,
        "counting_policy": counting_policy,
        "violation_count": int(session_row["violation_count"] or 0),
        "timestamp": event_timestamp,
    }
    try:
        await publish_exam_monitor_event(effective_exam_id, broadcast_payload)
    except Exception:
        logger.exception(
            "Violation broadcast failed exam_id=%s session_id=%s event_type=%s",
            effective_exam_id,
            int(session_row["id"]),
            normalized_event_type,
        )

    violation_count = int(session_row["violation_count"] or 0)
    warning = get_violation_warning_message(violation_count)

    return ViolationResponse(
        status="logged",
        violation_count=violation_count,
        warning=warning,
    )
