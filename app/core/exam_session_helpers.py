"""
Helpers for exam session timing and answer metadata normalization.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from app.models.session import ExamSession


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
