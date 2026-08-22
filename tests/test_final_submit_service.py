from types import SimpleNamespace

import pytest

from app.api import final_submit
from app.schemas.answer import ExamSubmitRequest, ExamSubmitResponse
from app.services import final_submit_service


class _FakeFinalSubmitService:
    def __init__(self):
        self.called = None

    async def submit_exam(self, submit_data, request):
        self.called = (submit_data.session_id, request)
        return ExamSubmitResponse(
            session_id=submit_data.session_id,
            status="submitted",
            message="ok",
        )


@pytest.mark.asyncio
async def test_submit_exam_endpoint_routes_to_final_submit_service(monkeypatch) -> None:
    fake_service = _FakeFinalSubmitService()
    monkeypatch.setattr(final_submit, "get_final_submit_service", lambda db, user: fake_service)

    response = await final_submit.submit_exam(
        ExamSubmitRequest(session_id=123),
        request=None,
        current_user=SimpleNamespace(id=7, username="student"),
        db=None,
    )

    assert response.status == "submitted"
    assert fake_service.called == (123, None)


@pytest.mark.asyncio
async def test_final_submit_preflushes_runtime_answer_buffer_when_enabled(monkeypatch) -> None:
    flushed = {}

    async def fake_flush(db, session_id):
        flushed["db"] = db
        flushed["session_id"] = session_id
        return 2

    monkeypatch.setattr(final_submit_service, "_answer_write_mode", lambda: "direct")
    monkeypatch.setattr(final_submit_service, "is_runtime_answer_buffer_enabled", lambda: True)
    monkeypatch.setattr(final_submit_service, "flush_runtime_answer_buffer_for_session", fake_flush)

    fake_db = SimpleNamespace()
    service = final_submit_service.FinalSubmitService(
        db=fake_db,
        current_user=SimpleNamespace(id=7, username="student"),
    )

    await service._flush_answer_buffers_before_submit(123)

    assert flushed == {"db": fake_db, "session_id": 123}


@pytest.mark.asyncio
async def test_final_submit_flush_ignores_percentage_zero_when_capability_enabled(monkeypatch) -> None:
    flushed = {}

    async def fake_flush(db, session_id):
        flushed["db"] = db
        flushed["session_id"] = session_id
        return 1

    monkeypatch.setattr(final_submit_service.settings, "answer_write_mode", "hybrid")
    monkeypatch.setattr(final_submit_service.settings, "answer_queue_enabled", True)
    monkeypatch.setattr(final_submit_service.settings, "answer_queue_percentage", 0)
    monkeypatch.setattr(final_submit_service, "flush_runtime_answer_buffer_for_session", fake_flush)

    fake_db = SimpleNamespace()
    service = final_submit_service.FinalSubmitService(
        db=fake_db,
        current_user=SimpleNamespace(id=7, username="student"),
    )

    await service._flush_answer_buffers_before_submit(123)

    assert flushed == {"db": fake_db, "session_id": 123}


class _MappingResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def one_or_none(self):
        return self._row


class _ProbeDb:
    def __init__(self, row):
        self.row = row
        self.rollbacks = 0

    async def execute(self, _stmt):
        return _MappingResult(self.row)

    async def rollback(self):
        self.rollbacks += 1


@pytest.mark.asyncio
async def test_final_submit_is_idempotent_after_submitted(monkeypatch) -> None:
    async def ok_rate_limit(_limiter, _key):
        return True, 99

    monkeypatch.setattr(final_submit_service, "check_rate_limit", ok_rate_limit)
    service = final_submit_service.FinalSubmitService(
        db=_ProbeDb(
            {
                "session_id": 123,
                "exam_id": 55,
                "status": "submitted",
                "score": 88.0,
                "show_results": True,
                "passing_score": 70.0,
            }
        ),
        current_user=SimpleNamespace(id=7, username="student"),
    )

    response = await service.submit_exam(ExamSubmitRequest(session_id=123), request=None)

    assert response.status == "submitted"
    assert response.score == 88.0
    assert response.passed is True
    assert response.message == "Sesi sudah pernah dikumpulkan."


@pytest.mark.asyncio
async def test_final_submit_runtime_buffer_flush_failure_returns_503(monkeypatch) -> None:
    async def failing_flush(_db, _session_id):
        raise RuntimeError("redis/db pressure")

    fake_db = SimpleNamespace(rollback_called=False)

    async def rollback():
        fake_db.rollback_called = True

    fake_db.rollback = rollback
    monkeypatch.setattr(final_submit_service, "_answer_write_mode", lambda: "direct")
    monkeypatch.setattr(final_submit_service, "is_runtime_answer_buffer_enabled", lambda: True)
    monkeypatch.setattr(final_submit_service, "flush_runtime_answer_buffer_for_session", failing_flush)
    service = final_submit_service.FinalSubmitService(
        db=fake_db,
        current_user=SimpleNamespace(id=7, username="student"),
    )

    with pytest.raises(Exception) as exc_info:
        await service._flush_answer_buffers_before_submit(123)

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers["Retry-After"] == "1"
    assert fake_db.rollback_called is True


@pytest.mark.asyncio
async def test_final_submit_post_submit_monitoring_failures_are_best_effort(monkeypatch) -> None:
    async def failing_invalidate(_exam_id):
        raise RuntimeError("cache down")

    async def failing_get_session(_session_id):
        raise RuntimeError("redis down")

    async def failing_publish(_exam_id, _payload):
        raise RuntimeError("websocket down")

    monkeypatch.setattr(final_submit_service, "invalidate_exam_results_cache", failing_invalidate)
    monkeypatch.setattr(final_submit_service, "get_session_data", failing_get_session)
    monkeypatch.setattr(final_submit_service, "_publish_exam_monitor_event", failing_publish)

    service = final_submit_service.FinalSubmitService(
        db=SimpleNamespace(),
        current_user=SimpleNamespace(id=7, username="student"),
    )

    await service._after_submit_best_effort(
        SimpleNamespace(id=123, exam_id=55, violation_count=0),
        percentage=90.0,
    )
