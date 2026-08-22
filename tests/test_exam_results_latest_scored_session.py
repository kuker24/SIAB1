from datetime import datetime, timedelta, timezone

from app.api.exams import _pick_latest_scored_exam_session_per_user


def _dt(offset_minutes: int) -> datetime:
    return datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=offset_minutes)


def test_pick_latest_scored_session_prefers_older_scored_over_newer_null() -> None:
    rows = [
        {
            "session_id": 200,
            "user_id": 10,
            "score": None,
            "end_time": _dt(30),
        },
        {
            "session_id": 150,
            "user_id": 10,
            "score": 78.4,
            "end_time": _dt(20),
        },
    ]

    selected = _pick_latest_scored_exam_session_per_user(rows)
    assert len(selected) == 1
    assert selected[0]["session_id"] == 150
    assert selected[0]["score"] == 78.4


def test_pick_latest_scored_session_falls_back_to_latest_when_all_null() -> None:
    rows = [
        {
            "session_id": 301,
            "user_id": 20,
            "score": None,
            "end_time": _dt(45),
        },
        {
            "session_id": 299,
            "user_id": 20,
            "score": None,
            "end_time": _dt(15),
        },
    ]

    selected = _pick_latest_scored_exam_session_per_user(rows)
    assert len(selected) == 1
    assert selected[0]["session_id"] == 301
    assert selected[0]["score"] is None


def test_pick_latest_scored_session_keeps_newest_selected_rows_first() -> None:
    rows = [
        {
            "session_id": 420,
            "user_id": 1,
            "score": 88.0,
            "end_time": _dt(10),
        },
        {
            "session_id": 410,
            "user_id": 2,
            "score": 90.0,
            "end_time": _dt(50),
        },
    ]

    selected = _pick_latest_scored_exam_session_per_user(rows)
    assert [int(row["user_id"]) for row in selected] == [2, 1]
