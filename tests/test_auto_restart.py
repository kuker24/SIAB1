from datetime import datetime, timezone

from app.core.auto_restart import WIB_TZ, _build_status_from_schedule, _normalize_schedule, _parse_wib_datetime


def test_parse_wib_datetime_supports_basic_format() -> None:
    parsed = _parse_wib_datetime("2026-03-07 08:15")
    assert parsed.tzinfo == WIB_TZ
    assert parsed.year == 2026
    assert parsed.month == 3
    assert parsed.day == 7
    assert parsed.hour == 8
    assert parsed.minute == 15
    assert parsed.second == 0


def test_build_status_marks_due_without_recurring_loop() -> None:
    schedule = _normalize_schedule(
        {
            "enabled": True,
            "entries": [
                {
                    "id": "e_due",
                    "scheduled_at_wib": "2026-03-06T07:30:00+07:00",
                    "status": "pending",
                },
                {
                    "id": "e_next",
                    "scheduled_at_wib": "2026-03-06T09:00:00+07:00",
                    "status": "pending",
                },
            ],
        }
    )
    now_utc = datetime(2026, 3, 6, 1, 0, tzinfo=timezone.utc)  # 08:00 WIB
    status = _build_status_from_schedule(schedule, now_utc=now_utc)
    assert status["state"] == "due"
    assert status["pending_count"] == 2
    assert status["due_count"] == 1
    assert status["next_run_at_wib"] == "2026-03-06T09:00:00+07:00"


def test_build_status_disabled() -> None:
    schedule = _normalize_schedule({"enabled": False, "entries": []})
    status = _build_status_from_schedule(schedule)
    assert status["state"] == "disabled"
    assert status["pending_count"] == 0
    assert status["due_count"] == 0
