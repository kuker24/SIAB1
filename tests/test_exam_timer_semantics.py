from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.exam_session_helpers import (
    CLOSE_EXPIRED_POLICY,
    STUDENT_TIMER_POLICY,
    TIMEOUT_TOLERANCE_SECONDS,
    STALE_PAUSE_GRACE_SECONDS,
    TimerContext,
    calculate_effective_timer,
    evaluate_timer,
)


NOW = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
START = NOW - timedelta(minutes=90)


def _ctx(**overrides) -> TimerContext:
    values = dict(
        started_at=START,
        duration_seconds=60 * 60,
        accumulated_paused_seconds=0,
        session_paused=False,
        session_paused_at=None,
        exam_globally_paused=False,
        exam_globally_paused_at=None,
        exam_end=NOW + timedelta(hours=2),
    )
    values.update(overrides)
    return TimerContext(**values)


def test_student_remaining_ignores_timeout_tolerance() -> None:
    started = NOW - timedelta(minutes=10)
    result = evaluate_timer(_ctx(started_at=started), STUDENT_TIMER_POLICY, now=NOW)
    elapsed, remaining = calculate_effective_timer(
        started_at=started,
        total_seconds=60 * 60,
        total_paused_seconds=0,
        now=NOW,
    )
    assert result.effective_elapsed == elapsed == 10 * 60
    assert result.remaining == remaining == 50 * 60
    assert result.should_close is False
    overtime = evaluate_timer(_ctx(), STUDENT_TIMER_POLICY, now=NOW)
    assert overtime.remaining == 0
    assert overtime.should_close is True


def test_active_pause_blocks_close_expired() -> None:
    result = evaluate_timer(
        _ctx(session_paused=True, session_paused_at=NOW - timedelta(minutes=10)),
        CLOSE_EXPIRED_POLICY,
        now=NOW,
    )
    assert result.pause_active is True
    assert result.stale_pause_detected is False
    assert result.should_close is False


def test_stale_pause_after_grace_closes() -> None:
    exam_end = NOW - timedelta(hours=7)
    result = evaluate_timer(
        _ctx(
            exam_end=exam_end,
            exam_globally_paused=True,
            exam_globally_paused_at=exam_end - timedelta(minutes=5),
        ),
        CLOSE_EXPIRED_POLICY,
        now=NOW,
    )
    assert result.stale_pause_detected is True
    assert result.expired_by_exam_end is True
    assert result.should_close is True


def test_duration_requires_five_minute_tolerance() -> None:
    just_inside = evaluate_timer(
        _ctx(started_at=NOW - timedelta(minutes=64), exam_end=None),
        CLOSE_EXPIRED_POLICY,
        now=NOW,
    )
    just_outside = evaluate_timer(
        _ctx(started_at=NOW - timedelta(minutes=66), exam_end=None),
        CLOSE_EXPIRED_POLICY,
        now=NOW,
    )
    assert just_inside.should_close is False
    assert just_outside.expired_by_duration is True
    assert just_outside.should_close is True


def test_exam_end_includes_pause_and_tolerance() -> None:
    exam_end = NOW - timedelta(minutes=3)
    result = evaluate_timer(
        _ctx(
            started_at=NOW - timedelta(minutes=20),
            duration_seconds=120 * 60,
            accumulated_paused_seconds=120,
            exam_end=exam_end,
        ),
        CLOSE_EXPIRED_POLICY,
        now=NOW,
    )
    assert result.should_close is False
    expired = evaluate_timer(
        _ctx(
            started_at=NOW - timedelta(minutes=20),
            duration_seconds=120 * 60,
            accumulated_paused_seconds=0,
            exam_end=NOW - timedelta(minutes=6),
        ),
        CLOSE_EXPIRED_POLICY,
        now=NOW,
    )
    assert expired.expired_by_exam_end is True
    assert expired.should_close is True


def test_close_expired_scheduler_uses_canonical_timer() -> None:
    source = Path("app/tasks/scheduler.py").read_text(encoding="utf-8")
    assert "evaluate_timer(" in source
    assert "CLOSE_EXPIRED_POLICY" in source
    assert "timeout_tolerance_seconds = 5 * 60" not in source
    assert TIMEOUT_TOLERANCE_SECONDS == 300
    assert STALE_PAUSE_GRACE_SECONDS == 6 * 60 * 60
