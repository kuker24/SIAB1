from app.api.analytics import _pick_latest_session_with_score_per_user


def test_pick_latest_session_prefers_non_null_score_over_newer_null() -> None:
    # Simulate rows already sorted by user_id, end_time desc, session_id desc
    rows = [
        {"session_id": 12, "user_id": 101, "score": None},  # newest but not graded
        {"session_id": 10, "user_id": 101, "score": 78.5},  # older and graded
    ]

    selected = _pick_latest_session_with_score_per_user(rows)
    assert selected[101]["session_id"] == 10
    assert selected[101]["score"] == 78.5


def test_pick_latest_session_falls_back_to_latest_when_all_scores_null() -> None:
    rows = [
        {"session_id": 22, "user_id": 202, "score": None},  # latest
        {"session_id": 20, "user_id": 202, "score": None},
    ]

    selected = _pick_latest_session_with_score_per_user(rows)
    assert selected[202]["session_id"] == 22
    assert selected[202]["score"] is None
