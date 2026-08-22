from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import sqlalchemy
from fastapi import HTTPException

from app.api import answer_sync, exam_answer_sync
from app.schemas.answer import (
    AnswerJournalEvent,
    AnswerJournalSyncRequest,
    AnswerJournalSyncResponse,
    AnswerResponse,
    AnswerSubmit,
    AutoSaveRequest,
    AutoSaveResponse,
)
from app.schemas.answer_sync import BatchAnswerItem, BatchAutoSaveRequest
from app.services import answer_sync_service


class _FakeAnswerSyncService:
    def __init__(self):
        self.called = None

    async def accept_single_answer(self, answer_data, request):
        self.called = ("single", answer_data.session_id, request)
        return AnswerResponse(
            status="saved",
            question_id=answer_data.question_id,
            message="Jawaban berhasil disimpan",
        )

    async def accept_legacy_autosave(self, save_data):
        self.called = ("legacy_autosave", save_data.session_id)
        return AutoSaveResponse(
            status="success",
            saved_count=len(save_data.answers),
            timestamp=datetime.now(timezone.utc),
        )

    async def accept_batch(self, batch_data):
        self.called = ("batch", batch_data.session_id)
        return {
            "status": "saved_to_db",
            "queued_count": len(batch_data.answers),
            "queue_id": "test",
            "timestamp": datetime.now(timezone.utc),
        }

    async def accept_journal_events(self, sync_data):
        self.called = ("journal", sync_data.session_id)
        return AnswerJournalSyncResponse(
            status="ok",
            accepted=0,
            duplicates=0,
            invalid=0,
            applied_question_count=0,
            acks=[],
            server_time=datetime.now(timezone.utc),
        )


@pytest.mark.asyncio
async def test_submit_answer_endpoint_routes_to_answer_sync_service(monkeypatch) -> None:
    fake_service = _FakeAnswerSyncService()
    monkeypatch.setattr(answer_sync, "get_answer_sync_service", lambda db, user: fake_service)

    response = await answer_sync.submit_answer(
        AnswerSubmit(session_id=123, question_id=45, selected_option_id=9),
        request="request-object",
        current_user=SimpleNamespace(id=7),
        db=None,
    )

    assert response.status == "saved"
    assert fake_service.called == ("single", 123, "request-object")


@pytest.mark.asyncio
async def test_legacy_autosave_endpoint_routes_to_answer_sync_service(monkeypatch) -> None:
    fake_service = _FakeAnswerSyncService()
    monkeypatch.setattr(exam_answer_sync, "get_answer_sync_service", lambda db, user: fake_service)

    response = await exam_answer_sync.auto_save_answers(
        AutoSaveRequest(
            session_id=123,
            answers={1: "A"},
            timestamp=datetime.now(timezone.utc),
        ),
        request=None,
        current_user=SimpleNamespace(id=7),
        db=None,
    )

    assert response.status == "success"
    assert fake_service.called == ("legacy_autosave", 123)


@pytest.mark.asyncio
async def test_batch_autosave_endpoint_routes_to_answer_sync_service(monkeypatch) -> None:
    fake_service = _FakeAnswerSyncService()
    monkeypatch.setattr(exam_answer_sync, "get_answer_sync_service", lambda db, user: fake_service)

    response = await exam_answer_sync.auto_save_batch(
        BatchAutoSaveRequest(
            session_id=123,
            answers=[BatchAnswerItem(question_id=1, selected_option_id=2)],
        ),
        request=None,
        current_user=SimpleNamespace(id=7),
        db=None,
    )

    assert response["status"] == "saved_to_db"
    assert fake_service.called == ("batch", 123)


@pytest.mark.asyncio
async def test_answer_journal_endpoint_routes_to_answer_sync_service(monkeypatch) -> None:
    fake_service = _FakeAnswerSyncService()
    monkeypatch.setattr(exam_answer_sync, "get_answer_sync_service", lambda db, user: fake_service)

    response = await exam_answer_sync.sync_answer_journal(
        AnswerJournalSyncRequest(session_id=123, events=[]),
        current_user=SimpleNamespace(id=7),
        db=None,
    )

    assert response.status == "ok"
    assert fake_service.called == ("journal", 123)


class _FirstResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return SimpleNamespace(all=lambda: [self._value] if self._value is not None else [])


class _RowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _FakeSingleAnswerDb:
    def __init__(self, results=None, exc=None):
        self.results = list(results or [])
        self.exc = exc
        self.commits = 0
        self.rollbacks = 0
        self.execute_calls = 0

    async def execute(self, _stmt, *_args, **_kwargs):
        self.execute_calls += 1
        if self.exc is not None:
            raise self.exc
        if not self.results:
            return _FirstResult(None)
        return self.results.pop(0)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    def add(self, _obj):
        pass


def _single_answer_service(db):
    return answer_sync_service.AnswerSyncService(
        db=db,
        current_user=SimpleNamespace(id=7, username="student01"),
    )


def _patch_single_answer_common(monkeypatch, *, status="in_progress"):
    async def ok_rate_limit(_limiter, _key):
        return True, 99

    async def ok_seb(_request, _exam_id, _db, require_seb=True):
        assert require_seb is True
        return True

    async def question_payload(_db, *, exam_id, question_id):
        return {
            "id": question_id,
            "exam_id": exam_id,
            "question_type": "multiple_choice",
            "pgk_type": None,
            "points": 1.0,
        }

    monkeypatch.setattr(answer_sync_service, "check_rate_limit", ok_rate_limit)
    monkeypatch.setattr(answer_sync_service, "validate_seb_headers", ok_seb)
    monkeypatch.setattr(answer_sync_service, "get_question_validation_payload_cached", question_payload)
    monkeypatch.setattr(
        answer_sync_service,
        "validate_answer_with_cached_payload",
        lambda *_args, **_kwargs: (True, 1.0),
    )
    monkeypatch.setattr(answer_sync_service, "should_publish_progress_update", lambda _session_id: False)
    monkeypatch.setattr(answer_sync_service, "_answer_write_mode", lambda: "direct")
    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: False)
    return status


@pytest.mark.asyncio
async def test_single_answer_submitted_session_is_idempotent(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    db = _FakeSingleAnswerDb(results=[_FirstResult((123, 55, "submitted"))])

    response = await _single_answer_service(db).accept_single_answer(
        AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
        request=None,
    )

    assert response.status == "saved"
    assert "diabaikan" in response.message
    assert db.execute_calls == 1


@pytest.mark.asyncio
async def test_single_answer_invalid_session_raises_404(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    db = _FakeSingleAnswerDb(results=[_FirstResult(None)])

    with pytest.raises(HTTPException) as exc_info:
        await _single_answer_service(db).accept_single_answer(
            AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
            request=None,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_single_answer_non_in_progress_session_raises_400(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    db = _FakeSingleAnswerDb(results=[_FirstResult((123, 55, "terminated"))])

    with pytest.raises(HTTPException) as exc_info:
        await _single_answer_service(db).accept_single_answer(
            AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
            request=None,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_single_answer_transient_db_error_returns_503_retry_after(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    db = _FakeSingleAnswerDb(exc=sqlalchemy.exc.TimeoutError("busy"))

    with pytest.raises(HTTPException) as exc_info:
        await _single_answer_service(db).accept_single_answer(
            AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
            request=None,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers["Retry-After"] == "1"


@pytest.mark.asyncio
async def test_single_answer_direct_write_updates_runtime_count(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    wrote = {}
    runtime = {}

    async def fake_write(self, *, session_id, question_id, write_fields):
        wrote["session_id"] = session_id
        wrote["question_id"] = question_id
        wrote["is_correct"] = write_fields["is_correct"]
        wrote["points_earned"] = write_fields["points_earned"]

    async def fake_add_answered(session_id, question_ids):
        runtime["added"] = (session_id, question_ids)
        return 4

    async def fake_update_snapshot(session_id, **kwargs):
        runtime["snapshot"] = (session_id, kwargs)

    async def fake_update_session_answers(session_id, answers):
        runtime["answers"] = (session_id, answers)

    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_write_single_answer_direct", fake_write)
    monkeypatch.setattr(answer_sync_service, "add_answered_questions_and_count", fake_add_answered)
    monkeypatch.setattr(answer_sync_service, "update_runtime_snapshot_answered_count", fake_update_snapshot)
    monkeypatch.setattr(answer_sync_service, "update_session_answers", fake_update_session_answers)

    locked_session = SimpleNamespace(id=123, exam_id=55, status="in_progress")
    db = _FakeSingleAnswerDb(
        results=[
            _FirstResult((123, 55, "in_progress")),
            _ScalarResult(None),
            _ScalarResult(locked_session),
        ]
    )

    response = await _single_answer_service(db).accept_single_answer(
        AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
        request=None,
    )

    assert response.status == "saved"
    assert wrote == {"session_id": 123, "question_id": 9, "is_correct": True, "points_earned": 1.0}
    assert runtime["added"] == (123, [9])
    assert runtime["snapshot"][1]["answered_count"] == 4
    assert runtime["answers"] == (123, {"9": True})


@pytest.mark.asyncio
async def test_single_answer_peak_mode_skips_progress_broadcast(monkeypatch) -> None:
    monkeypatch.setattr(answer_sync_service.settings, "exam_peak_mode", True)

    def fail_should_publish(_session_id):
        raise AssertionError("progress throttle should not run in peak mode")

    async def fail_publish(*_args, **_kwargs):
        raise AssertionError("progress publish should not run in peak mode")

    monkeypatch.setattr(answer_sync_service, "should_publish_progress_update", fail_should_publish)
    monkeypatch.setattr(answer_sync_service, "_publish_exam_monitor_event", fail_publish)

    db = _FakeSingleAnswerDb()
    await _single_answer_service(db)._publish_progress_if_needed(
        session_id=123,
        exam_id=55,
        answered_count_runtime=1,
    )

    assert db.execute_calls == 0
    assert db.commits == 0


@pytest.mark.asyncio
async def test_single_answer_hybrid_buffer_path_does_not_call_direct_write(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    called = {}

    class _FakeRuntimeBuffer:
        def __init__(self, db, current_user):
            called["init"] = (db, current_user.id)

        async def accept_single_answer(self, **kwargs):
            called["buffer"] = kwargs
            return 1

    async def fail_direct(*_args, **_kwargs):
        raise AssertionError("direct write should not run in hybrid buffer mode")

    monkeypatch.setattr(answer_sync_service, "_answer_write_mode", lambda: "hybrid")
    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: True)
    monkeypatch.setattr(answer_sync_service, "AnswerRuntimeBufferService", _FakeRuntimeBuffer)
    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_write_single_answer_direct", fail_direct)
    monkeypatch.setattr(answer_sync_service, "add_answered_questions_and_count", lambda *_args, **_kwargs: None)

    async def fake_update_session_answers(_session_id, _answers):
        return None

    monkeypatch.setattr(answer_sync_service, "update_session_answers", fake_update_session_answers)

    locked_session = SimpleNamespace(id=123, exam_id=55, status="in_progress")
    db = _FakeSingleAnswerDb(
        results=[
            _FirstResult((123, 55, "in_progress")),
            _ScalarResult(None),
            _ScalarResult(locked_session),
        ]
    )

    response = await _single_answer_service(db).accept_single_answer(
        AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
        request=None,
    )

    assert response.status == "saved"
    assert called["buffer"]["session"] is locked_session


@pytest.mark.asyncio
async def test_single_answer_hybrid_percentage_false_falls_back_to_direct_write(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    wrote = {}

    class _UnexpectedRuntimeBuffer:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("runtime buffer should not initialize when session is not selected")

    async def fake_write(self, *, session_id, question_id, write_fields):
        wrote["session_id"] = session_id
        wrote["question_id"] = question_id

    async def fake_update_session_answers(_session_id, _answers):
        return None

    monkeypatch.setattr(answer_sync_service, "_answer_write_mode", lambda: "hybrid")
    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: False)
    monkeypatch.setattr(answer_sync_service, "AnswerRuntimeBufferService", _UnexpectedRuntimeBuffer)
    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_write_single_answer_direct", fake_write)
    monkeypatch.setattr(answer_sync_service, "update_session_answers", fake_update_session_answers)
    monkeypatch.setattr(answer_sync_service, "add_answered_questions_and_count", lambda *_args, **_kwargs: None)

    locked_session = SimpleNamespace(id=123, exam_id=55, status="in_progress")
    db = _FakeSingleAnswerDb(
        results=[
            _FirstResult((123, 55, "in_progress")),
            _ScalarResult(None),
            _ScalarResult(locked_session),
        ]
    )

    response = await _single_answer_service(db).accept_single_answer(
        AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
        request=None,
    )

    assert response.status == "saved"
    assert wrote == {"session_id": 123, "question_id": 9}


async def _noop_update_session_answers(_session_id, _answers):
    return None


async def _fake_runtime_count(self, session_id, question_ids, log_prefix):
    return len(question_ids)


@pytest.mark.asyncio
async def test_single_answer_queue_percentage_false_falls_back_to_direct_write(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    wrote = {}

    async def fail_enqueue(_payload):
        raise AssertionError("queue enqueue should not run when session is not selected")

    async def fake_write(self, *, session_id, question_id, write_fields):
        wrote["session_id"] = session_id
        wrote["question_id"] = question_id
        wrote["selected_option_id"] = write_fields["selected_option_id"]

    monkeypatch.setattr(answer_sync_service, "_answer_write_mode", lambda: "queue")
    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: False)
    monkeypatch.setattr(answer_sync_service, "enqueue_answer_payload", fail_enqueue)
    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_write_single_answer_direct", fake_write)
    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_update_runtime_answered_count", _fake_runtime_count)
    monkeypatch.setattr(answer_sync_service, "update_session_answers", _noop_update_session_answers)

    locked_session = SimpleNamespace(id=123, exam_id=55, status="in_progress")
    db = _FakeSingleAnswerDb(
        results=[
            _FirstResult((123, 55, "in_progress")),
            _ScalarResult(None),
            _ScalarResult(locked_session),
        ]
    )

    response = await _single_answer_service(db).accept_single_answer(
        AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
        request=None,
    )

    assert response.status == "saved"
    assert wrote == {"session_id": 123, "question_id": 9, "selected_option_id": 2}


@pytest.mark.asyncio
async def test_single_answer_queue_percentage_true_enqueues_without_direct_write(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    queued = {}

    async def fake_enqueue(payload):
        queued.update(payload)

    async def fail_direct(*_args, **_kwargs):
        raise AssertionError("direct write should not run for selected queue-mode session")

    monkeypatch.setattr(answer_sync_service, "_answer_write_mode", lambda: "queue")
    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: True)
    monkeypatch.setattr(answer_sync_service, "enqueue_answer_payload", fake_enqueue)
    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_write_single_answer_direct", fail_direct)
    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_update_runtime_answered_count", _fake_runtime_count)
    monkeypatch.setattr(answer_sync_service, "update_session_answers", _noop_update_session_answers)

    locked_session = SimpleNamespace(id=123, exam_id=55, status="in_progress")
    db = _FakeSingleAnswerDb(
        results=[
            _FirstResult((123, 55, "in_progress")),
            _ScalarResult(None),
            _ScalarResult(locked_session),
        ]
    )

    response = await _single_answer_service(db).accept_single_answer(
        AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
        request=None,
    )

    assert response.status == "saved"
    assert queued["session_id"] == 123
    assert queued["exam_id"] == 55
    assert queued["user_id"] == 7
    assert queued["question_id"] == 9
    assert queued["selected_option_id"] == 2
    assert queued["selected_option_ids"] is None
    assert queued["answer_text"] is None
    assert queued["statement_answers"] is None
    assert queued["is_correct"] is True
    assert queued["points_earned"] == 1.0
    assert "answered_at" in queued


@pytest.mark.asyncio
async def test_single_answer_queue_enqueue_failure_falls_back_to_direct_write(monkeypatch) -> None:
    _patch_single_answer_common(monkeypatch)
    wrote = {}

    async def fail_enqueue(_payload):
        raise RuntimeError("redis busy")

    async def fake_write(self, *, session_id, question_id, write_fields):
        wrote["session_id"] = session_id
        wrote["question_id"] = question_id
        wrote["selected_option_id"] = write_fields["selected_option_id"]

    monkeypatch.setattr(answer_sync_service, "_answer_write_mode", lambda: "queue")
    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: True)
    monkeypatch.setattr(answer_sync_service, "enqueue_answer_payload", fail_enqueue)
    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_write_single_answer_direct", fake_write)
    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_update_runtime_answered_count", _fake_runtime_count)
    monkeypatch.setattr(answer_sync_service, "update_session_answers", _noop_update_session_answers)

    locked_session = SimpleNamespace(id=123, exam_id=55, status="in_progress")
    db = _FakeSingleAnswerDb(
        results=[
            _FirstResult((123, 55, "in_progress")),
            _ScalarResult(None),
            _ScalarResult(locked_session),
        ]
    )

    response = await _single_answer_service(db).accept_single_answer(
        AnswerSubmit(session_id=123, question_id=9, selected_option_id=2),
        request=None,
    )

    assert response.status == "saved"
    assert wrote == {"session_id": 123, "question_id": 9, "selected_option_id": 2}


class _FakeRuntimeBufferService:
    def __init__(self, db, current_user):
        self.db = db
        self.current_user = current_user

    async def accept_batch(self, batch_data):
        return {
            "status": "buffered",
            "queued_count": len(batch_data.answers),
            "queue_id": "redis-test",
            "timestamp": datetime.now(timezone.utc),
        }

    async def accept_journal_events(self, sync_data, accepted_events):
        return len(accepted_events)


class _FakeRedis:
    def pipeline(self):
        return self

    def sismember(self, *_args, **_kwargs):
        return self

    async def execute(self):
        return [False]

    async def sadd(self, *_args, **_kwargs):
        return 1

    async def expire(self, *_args, **_kwargs):
        return True


@pytest.mark.asyncio
async def test_batch_autosave_hybrid_percentage_true_routes_to_runtime_buffer(monkeypatch) -> None:
    called = {}

    class _RuntimeBuffer(_FakeRuntimeBufferService):
        async def accept_batch(self, batch_data):
            called["batch"] = batch_data.session_id
            return await super().accept_batch(batch_data)

    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: True)
    monkeypatch.setattr(answer_sync_service, "AnswerRuntimeBufferService", _RuntimeBuffer)

    db = _FakeSingleAnswerDb(results=[_ScalarResult(SimpleNamespace(id=123, exam_id=55))])
    service = _single_answer_service(db)
    batch_data = BatchAutoSaveRequest(
        session_id=123,
        answers=[BatchAnswerItem(question_id=1, selected_option_id=2)],
    )

    result = await service.accept_batch(batch_data)

    assert result["status"] == "buffered"
    assert called["batch"] == 123
    assert db.execute_calls == 1


@pytest.mark.asyncio
async def test_batch_autosave_hybrid_percentage_false_uses_direct_empty_path(monkeypatch) -> None:
    class _UnexpectedRuntimeBuffer:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("runtime buffer should not initialize when session is not selected")

    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: False)
    monkeypatch.setattr(answer_sync_service, "AnswerRuntimeBufferService", _UnexpectedRuntimeBuffer)

    db = _FakeSingleAnswerDb(results=[_ScalarResult(SimpleNamespace(id=123, exam_id=55))])
    service = _single_answer_service(db)
    batch_data = BatchAutoSaveRequest(session_id=123, answers=[])

    result = await service.accept_batch(batch_data)

    assert result["status"] == "no_changes"
    assert result["queued_count"] == 0


def _journal_request() -> AnswerJournalSyncRequest:
    return AnswerJournalSyncRequest(
        session_id=123,
        events=[
            AnswerJournalEvent(
                event_id="event000001",
                sequence=1,
                question_id=1,
                local_timestamp_ms=1000,
                selected_option_id=2,
            )
        ],
    )


@pytest.mark.asyncio
async def test_answer_journal_hybrid_percentage_true_routes_to_runtime_buffer(monkeypatch) -> None:
    called = {}

    class _RuntimeBuffer(_FakeRuntimeBufferService):
        async def accept_journal_events(self, sync_data, accepted_events):
            called["journal"] = (sync_data.session_id, len(accepted_events))
            return await super().accept_journal_events(sync_data, accepted_events)

    async def fake_get_redis():
        return _FakeRedis()

    monkeypatch.setattr(answer_sync_service, "get_redis", fake_get_redis)
    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: True)
    monkeypatch.setattr(answer_sync_service, "AnswerRuntimeBufferService", _RuntimeBuffer)

    db = _FakeSingleAnswerDb(
        results=[
            _ScalarResult(SimpleNamespace(id=123, exam_id=55)),
            _RowsResult([(1,)]),
        ]
    )
    response = await _single_answer_service(db).accept_journal_events(_journal_request())

    assert response.status == "ok"
    assert response.applied_question_count == 1
    assert called["journal"] == (123, 1)


@pytest.mark.asyncio
async def test_answer_journal_hybrid_percentage_false_uses_direct_path(monkeypatch) -> None:
    class _UnexpectedRuntimeBuffer:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("runtime buffer should not initialize when session is not selected")

    async def fake_get_redis():
        return _FakeRedis()

    async def fake_lock(_db, _session_id):
        return None

    async def fake_ensure(_db, *, session_id, user_id, lock_row=False):
        return SimpleNamespace(id=session_id, user_id=user_id, exam_id=55, status="in_progress")

    async def fake_update_session_answers(_session_id, _answers):
        return None

    async def fake_update_runtime_count(self, session_id, question_ids, log_prefix):
        return len(question_ids)

    monkeypatch.setattr(answer_sync_service, "get_redis", fake_get_redis)
    monkeypatch.setattr(answer_sync_service, "is_runtime_answer_buffer_enabled_for_session", lambda **_kwargs: False)
    monkeypatch.setattr(answer_sync_service, "AnswerRuntimeBufferService", _UnexpectedRuntimeBuffer)
    monkeypatch.setattr(answer_sync_service, "_acquire_session_write_lock", fake_lock)
    monkeypatch.setattr(answer_sync_service, "_ensure_session_in_progress_for_user", fake_ensure)
    monkeypatch.setattr(answer_sync_service, "update_session_answers", fake_update_session_answers)
    async def fake_load_existing_answers(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_load_existing_answers", fake_load_existing_answers)
    monkeypatch.setattr(answer_sync_service.AnswerSyncService, "_update_runtime_answered_count", fake_update_runtime_count)

    db = _FakeSingleAnswerDb(
        results=[
            _ScalarResult(SimpleNamespace(id=123, exam_id=55)),
            _RowsResult([(1,)]),
        ]
    )
    response = await _single_answer_service(db).accept_journal_events(_journal_request())

    assert response.status == "ok"
    assert response.accepted == 1
    assert response.applied_question_count == 1
    assert db.commits == 1


@pytest.mark.asyncio
async def test_progress_update_skips_db_count_fallback_during_peak_mode(monkeypatch) -> None:
    async def failing_answered_count(_session_id):
        raise RuntimeError("redis unavailable")

    async def unexpected_total_question_count(*_args, **_kwargs):
        raise AssertionError("question-count lookup should be skipped when progress count is unknown")

    async def unexpected_publish(*_args, **_kwargs):
        raise AssertionError("progress event should not publish without answered_count")

    monkeypatch.setattr(answer_sync_service, "should_publish_progress_update", lambda _session_id: True)
    monkeypatch.setattr(answer_sync_service, "get_answered_count_from_set", failing_answered_count)
    monkeypatch.setattr(answer_sync_service, "get_exam_question_count_cached", unexpected_total_question_count)
    monkeypatch.setattr(answer_sync_service, "_publish_exam_monitor_event", unexpected_publish)
    monkeypatch.setattr(answer_sync_service.settings, "exam_peak_mode", True)

    db = _FakeSingleAnswerDb()
    await _single_answer_service(db)._publish_progress_if_needed(
        session_id=123,
        exam_id=55,
        answered_count_runtime=None,
    )

    assert db.execute_calls == 0
    assert db.commits == 0


@pytest.mark.asyncio
async def test_progress_update_non_peak_publishes_when_runtime_count_exists(monkeypatch) -> None:
    published = {}

    async def fake_total_question_count(_db, _exam_id):
        return 40

    async def fake_publish(exam_id, payload):
        published["exam_id"] = exam_id
        published["payload"] = payload

    monkeypatch.setattr(answer_sync_service, "should_publish_progress_update", lambda _session_id: True)
    monkeypatch.setattr(answer_sync_service, "get_exam_question_count_cached", fake_total_question_count)
    monkeypatch.setattr(answer_sync_service, "_publish_exam_monitor_event", fake_publish)
    monkeypatch.setattr(answer_sync_service.settings, "exam_peak_mode", False)

    db = _FakeSingleAnswerDb()
    await _single_answer_service(db)._publish_progress_if_needed(
        session_id=123,
        exam_id=55,
        answered_count_runtime=10,
    )

    assert db.execute_calls == 0
    assert db.commits == 1
    assert published["exam_id"] == 55
    assert published["payload"]["progress"] == 25.0
    assert published["payload"]["answered_count"] == 10
