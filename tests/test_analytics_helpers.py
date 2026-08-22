from datetime import datetime, timezone

from app.core.analytics_helpers import build_local_day_windows, display_question_number


def test_question_number_keeps_existing_one_based_order_index():
    assert display_question_number(1, 1) == 1
    assert display_question_number(3, 2) == 3


def test_question_number_falls_back_when_order_index_missing_or_invalid():
    assert display_question_number(None, 1) == 1
    assert display_question_number(0, 2) == 2
    assert display_question_number(-4, 3) == 3


def test_build_local_day_windows_aligns_to_jakarta_calendar_days():
    windows = build_local_day_windows(
        1,
        now=datetime(2026, 3, 4, 16, 26, 0, tzinfo=timezone.utc),
    )

    assert [label for label, _, _ in windows] == ["2026-03-04"]
    assert windows[0][1].isoformat() == "2026-03-03T17:00:00+00:00"
    assert windows[0][2].isoformat() == "2026-03-04T17:00:00+00:00"
