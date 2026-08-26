"""
Helpers for exam session timing and answer metadata normalization.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from app.models.session import ExamSession

TIMEOUT_TOLERANCE_SECONDS = 5 * 60
STALE_PAUSE_GRACE_SECONDS = 6 * 60 * 60


def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class TimerPolicy:
    timeout_tolerance_seconds: int = 0
    stale_pause_grace_seconds: int = 0
    count_ongoing_pause_without_flag: bool = False
    block_expiry_while_pause_active: bool = False


STUDENT_TIMER_POLICY = TimerPolicy()
CLOSE_EXPIRED_POLICY = TimerPolicy(
    timeout_tolerance_seconds=TIMEOUT_TOLERANCE_SECONDS,
    stale_pause_grace_seconds=STALE_PAUSE_GRACE_SECONDS,
    count_ongoing_pause_without_flag=True,
    block_expiry_while_pause_active=True,
)


@dataclass(frozen=True)
class TimerContext:
    started_at: Optional[datetime]
    duration_seconds: int
    accumulated_paused_seconds: int = 0
    session_paused: bool = False
    session_paused_at: Optional[datetime] = None
    exam_globally_paused: bool = False
    exam_globally_paused_at: Optional[datetime] = None
    exam_end: Optional[datetime] = None


@dataclass(frozen=True)
class TimerResult:
    elapsed: int
    effective_elapsed: int
    remaining: int
    pause_active: bool
    stale_pause_detected: bool
    expired_by_duration: bool
    expired_by_exam_end: bool
    should_close: bool


def evaluate_timer(
    context: TimerContext,
    policy: TimerPolicy = STUDENT_TIMER_POLICY,
    now: Optional[datetime] = None,
) -> TimerResult:
    current = ensure_utc(now) or datetime.now(timezone.utc)
    started_at = ensure_utc(context.started_at)
    exam_end = ensure_utc(context.exam_end)
    duration_seconds = max(0, int(context.duration_seconds or 0))
    accumulated_paused = max(0, int(context.accumulated_paused_seconds or 0))
    pause_active = bool(context.session_paused or context.exam_globally_paused)
    stale_pause_detected = bool(
        policy.stale_pause_grace_seconds > 0
        and pause_active
        and exam_end is not None
        and current > exam_end + timedelta(seconds=policy.stale_pause_grace_seconds)
    )

    ongoing_pause_seconds = 0
    if not stale_pause_detected:
        session_paused_at = ensure_utc(context.session_paused_at)
        globally_paused_at = ensure_utc(context.exam_globally_paused_at)
        if policy.count_ongoing_pause_without_flag:
            if session_paused_at is not None:
                ongoing_pause_seconds = max(
                    ongoing_pause_seconds,
                    max(0, int((current - session_paused_at).total_seconds())),
                )
            if globally_paused_at is not None:
                ongoing_pause_seconds = max(
                    ongoing_pause_seconds,
                    max(0, int((current - globally_paused_at).total_seconds())),
                )
        else:
            if context.session_paused and session_paused_at is not None:
                ongoing_pause_seconds = max(
                    ongoing_pause_seconds,
                    max(0, int((current - session_paused_at).total_seconds())),
                )
            if context.exam_globally_paused and globally_paused_at is not None:
                ongoing_pause_seconds = max(
                    ongoing_pause_seconds,
                    max(0, int((current - globally_paused_at).total_seconds())),
                )

    effective_paused_seconds = accumulated_paused + ongoing_pause_seconds
    elapsed = (
        0
        if started_at is None
        else max(0, int((current - started_at).total_seconds()))
    )
    effective_elapsed = max(0, elapsed - effective_paused_seconds)
    remaining = max(0, duration_seconds - effective_elapsed)

    duration_expired = False
    exam_end_expired = stale_pause_detected
    if started_at is not None:
        duration_expired = effective_elapsed > (
            duration_seconds + int(policy.timeout_tolerance_seconds or 0)
        )
    if exam_end is not None and not exam_end_expired:
        exam_end_with_pause = exam_end + timedelta(
            seconds=effective_paused_seconds + int(policy.timeout_tolerance_seconds or 0)
        )
        exam_end_expired = current > exam_end_with_pause

    blocked = bool(
        policy.block_expiry_while_pause_active
        and pause_active
        and not stale_pause_detected
    )
    should_close = (
        started_at is not None
        and not blocked
        and (duration_expired or exam_end_expired)
    )
    return TimerResult(
        elapsed=elapsed,
        effective_elapsed=effective_elapsed,
        remaining=remaining,
        pause_active=pause_active,
        stale_pause_detected=stale_pause_detected,
        expired_by_duration=duration_expired,
        expired_by_exam_end=exam_end_expired,
        should_close=should_close,
    )


def parse_iso_datetime_utc(value: Any) -> Optional[datetime]:
    """Parse ISO datetime string into UTC-aware datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def resolve_timer_context(
    session: ExamSession,
    redis_data: Optional[Dict[str, Any]],
) -> Tuple[datetime, int, int]:
    """
    Resolve canonical timer inputs from Redis/DB.

    Returns:
    - started_at (first session start timestamp, idempotent)
    - total_seconds (exam duration in seconds)
    - total_paused_seconds (accumulated pause duration)
    """
    started_at = parse_iso_datetime_utc((redis_data or {}).get("started_at"))
    if started_at is None:
        started_at = session.start_time
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

    total_seconds = int((redis_data or {}).get("duration_seconds") or session.exam.duration_minutes * 60)
    redis_paused = int((redis_data or {}).get("total_paused_seconds") or 0)
    db_paused = int(session.total_paused_seconds or 0)
    accumulated_paused = max(0, max(redis_paused, db_paused))

    now_utc = datetime.now(timezone.utc)
    ongoing_pause_candidates = []

    if bool(getattr(session, "is_paused", False)) and getattr(session, "paused_at", None):
        paused_at = session.paused_at
        if paused_at.tzinfo is None:
            paused_at = paused_at.replace(tzinfo=timezone.utc)
        ongoing_pause_candidates.append(max(0, int((now_utc - paused_at).total_seconds())))

    exam = getattr(session, "exam", None)
    if exam and bool(getattr(exam, "is_globally_paused", False)) and getattr(exam, "globally_paused_at", None):
        global_paused_at = exam.globally_paused_at
        if global_paused_at.tzinfo is None:
            global_paused_at = global_paused_at.replace(tzinfo=timezone.utc)
        ongoing_pause_candidates.append(max(0, int((now_utc - global_paused_at).total_seconds())))

    ongoing_paused = max(ongoing_pause_candidates) if ongoing_pause_candidates else 0
    total_paused = max(0, accumulated_paused + ongoing_paused)
    return started_at, total_seconds, total_paused


def calculate_effective_timer(
    *,
    started_at: datetime,
    total_seconds: int,
    total_paused_seconds: int = 0,
    now: Optional[datetime] = None,
) -> Tuple[int, int]:
    """Return (effective_elapsed_seconds, remaining_seconds)."""
    current = now or datetime.now(timezone.utc)
    elapsed = max(0, int((current - started_at).total_seconds()))
    effective_elapsed = max(0, elapsed - max(0, int(total_paused_seconds or 0)))
    remaining = max(0, int(total_seconds) - effective_elapsed)
    return effective_elapsed, remaining


def safe_int(value: Any) -> Optional[int]:
    """Convert value to int safely, returning None on invalid input."""
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def merge_statement_answer_metadata(
    *,
    existing_metadata: Optional[Dict[str, Any]],
    incoming_metadata: Optional[Dict[str, Any]],
    incoming_statement_answers: Optional[Dict[str, bool]],
) -> Tuple[Dict[str, Any], Optional[Dict[str, bool]]]:
    """
    Merge answer metadata with table-validation semantics.

    Supports markers:
    - replace_statement_answers
    - delete_statement_answers
    """
    previous_metadata = dict(existing_metadata or {})
    normalized_incoming_metadata = dict(incoming_metadata or {})

    prev_statement_answers = previous_metadata.get("statement_answers")
    replace_statement_answers = bool(normalized_incoming_metadata.get("replace_statement_answers"))
    delete_statement_answers = bool(normalized_incoming_metadata.get("delete_statement_answers"))

    merged_statement_answers: Optional[Dict[str, bool]]
    if delete_statement_answers:
        merged_statement_answers = {}
    elif incoming_statement_answers is None:
        if replace_statement_answers:
            merged_statement_answers = {}
        elif isinstance(prev_statement_answers, dict):
            merged_statement_answers = prev_statement_answers
        else:
            merged_statement_answers = None
    elif replace_statement_answers:
        merged_statement_answers = incoming_statement_answers
    elif isinstance(prev_statement_answers, dict):
        merged_statement_answers = {**prev_statement_answers, **incoming_statement_answers}
    else:
        merged_statement_answers = incoming_statement_answers

    final_metadata = dict(previous_metadata)
    final_metadata.update(normalized_incoming_metadata)
    final_metadata.pop("replace_statement_answers", None)
    final_metadata.pop("delete_statement_answers", None)

    if isinstance(merged_statement_answers, dict):
        if merged_statement_answers:
            final_metadata["statement_answers"] = merged_statement_answers
        else:
            final_metadata.pop("statement_answers", None)

    return final_metadata, merged_statement_answers
