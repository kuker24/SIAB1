from pathlib import Path


ANSWER_SYNC_SERVICE_SOURCE = Path("app/services/answer_sync_service.py").read_text(
    encoding="utf-8"
)
MONITORING_SOURCE = Path("app/api/monitoring.py").read_text(encoding="utf-8")
RUNTIME_STATE_SOURCE = Path("app/core/exam_runtime_state.py").read_text(encoding="utf-8")


def test_runtime_state_module_exposes_bulk_helpers() -> None:
    assert "async def get_runtime_snapshots_bulk(" in RUNTIME_STATE_SOURCE
    assert "async def get_answered_counts_bulk(" in RUNTIME_STATE_SOURCE
    assert "async def add_answered_questions_and_count(" in RUNTIME_STATE_SOURCE


def test_submit_answer_updates_runtime_answered_counter() -> None:
    assert "add_answered_questions_and_count(" in ANSWER_SYNC_SERVICE_SOURCE
    assert "update_runtime_snapshot_answered_count(" in ANSWER_SYNC_SERVICE_SOURCE


def test_monitoring_uses_redis_first_answered_count_map() -> None:
    assert "async def _get_answered_count_map(" in MONITORING_SOURCE
    assert "get_runtime_snapshots_bulk" in MONITORING_SOURCE
    assert "get_answered_counts_bulk" in MONITORING_SOURCE
