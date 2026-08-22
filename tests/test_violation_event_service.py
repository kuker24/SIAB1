from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.schemas.answer import ViolationLog
from app.services import violation_event_service as service


class _FakeMappings:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return _FakeMappings(self._row)


class _FakeDb:
    def __init__(self, row):
        self.row = row
        self.execute_calls = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        return _FakeResult(self.row)


class _FakeRedis:
    def __init__(self, *, duplicate: bool = False):
        self.duplicate = duplicate
        self.pending = []
        self.hashes = {}
        self.lists = {}

    async def set(self, key, value, nx=False, ex=None):
        if self.duplicate:
            return False
        return True

    async def rpush(self, key, value):
        self.pending.append((key, value))
        return len(self.pending)

    async def expire(self, key, seconds):
        return True

    async def hincrby(self, key, field, amount):
        self.hashes.setdefault(key, {})[field] = self.hashes.setdefault(key, {}).get(field, 0) + amount
        return self.hashes[key][field]

    async def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)
        return len(self.lists[key])

    async def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start : end + 1]
        return True


class _FailingRedis(_FakeRedis):
    async def set(self, key, value, nx=False, ex=None):
        raise RuntimeError("redis down")


async def _fake_get_redis(redis):
    return redis


@pytest.fixture(autouse=True)
def _default_session_cache(monkeypatch):
    async def cache_miss(_session_id):
        return None

    async def store_noop(_session_id, _payload):
        return None

    monkeypatch.setattr(service, "get_session_data", cache_miss)
    monkeypatch.setattr(service, "store_session_data", store_noop)


def _cached_session(status="in_progress", user_id=7, violation_count=2):
    return {
        "session_id": 10,
        "user_id": user_id,
        "exam_id": 99,
        "status": status,
        "end_time": None,
        "violation_count": violation_count,
    }


def _session_row(status="in_progress", violation_count=2):
    return {
        "id": 10,
        "exam_id": 99,
        "violation_count": violation_count,
        "status": status,
        "end_time": None,
    }


def _violation_log():
    return ViolationLog(
        session_id=10,
        exam_id=0,
        event_type="tab_switch",
        event_data={"source": "apk", "reason": "test"},
        timestamp=datetime.now(timezone.utc),
        user_agent="SXB-Client test",
        screen_resolution="1080x1920",
    )


@pytest.mark.asyncio
async def test_enqueue_violation_event_queues_and_updates_runtime_cache(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(service, "get_redis", lambda: _fake_get_redis(fake_redis))

    fake_db = _FakeDb(_session_row())
    result = await service.enqueue_violation_event(
        fake_db,
        _violation_log(),
        SimpleNamespace(id=7, username="student01"),
    )

    assert result.status == "queued"
    assert fake_db.execute_calls == 1
    assert result.violation_count == 2
    assert fake_redis.pending[0][0] == service.PENDING_KEY
    assert service.AGGREGATE_KEY_TEMPLATE.format(exam_id=99) in fake_redis.hashes
    assert service.SESSION_KEY_TEMPLATE.format(session_id=10) in fake_redis.hashes


@pytest.mark.asyncio
async def test_enqueue_violation_event_dedupes_burst_without_queueing(monkeypatch) -> None:
    fake_redis = _FakeRedis(duplicate=True)
    monkeypatch.setattr(service, "get_redis", lambda: _fake_get_redis(fake_redis))

    result = await service.enqueue_violation_event(
        _FakeDb(_session_row()),
        _violation_log(),
        SimpleNamespace(id=7, username="student01"),
    )

    assert result.status == "duplicate"
    assert fake_redis.pending == []


@pytest.mark.asyncio
async def test_enqueue_violation_event_drops_best_effort_when_redis_fails(monkeypatch) -> None:
    fake_redis = _FailingRedis()
    monkeypatch.setattr(service, "get_redis", lambda: _fake_get_redis(fake_redis))

    result = await service.enqueue_violation_event(
        _FakeDb(_session_row()),
        _violation_log(),
        SimpleNamespace(id=7, username="student01"),
    )

    assert result.status == "dropped"
    assert result.violation_count == 2


@pytest.mark.asyncio
async def test_enqueue_violation_event_ignores_terminal_session(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(service, "get_redis", lambda: _fake_get_redis(fake_redis))

    result = await service.enqueue_violation_event(
        _FakeDb(_session_row(status="submitted")),
        _violation_log(),
        SimpleNamespace(id=7, username="student01"),
    )

    assert result.status == "ignored"
    assert fake_redis.pending == []


@pytest.mark.asyncio
async def test_enqueue_violation_event_cache_hit_skips_db_read(monkeypatch) -> None:
    fake_redis = _FakeRedis()

    async def cache_hit(_session_id):
        return _cached_session()

    monkeypatch.setattr(service, "get_session_data", cache_hit)
    monkeypatch.setattr(service, "get_redis", lambda: _fake_get_redis(fake_redis))
    fake_db = _FakeDb(_session_row())

    result = await service.enqueue_violation_event(
        fake_db,
        _violation_log(),
        SimpleNamespace(id=7, username="student01"),
    )

    assert result.status == "queued"
    assert fake_db.execute_calls == 0
    assert fake_redis.pending[0][0] == service.PENDING_KEY


@pytest.mark.asyncio
async def test_enqueue_violation_event_cache_user_mismatch_rejected(monkeypatch) -> None:
    async def wrong_user_cache(_session_id):
        return _cached_session(user_id=99)

    monkeypatch.setattr(service, "get_session_data", wrong_user_cache)

    with pytest.raises(HTTPException) as exc_info:
        await service.enqueue_violation_event(
            _FakeDb(_session_row()),
            _violation_log(),
            SimpleNamespace(id=7, username="student01"),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_enqueue_violation_event_terminal_cache_ignored_without_db(monkeypatch) -> None:
    fake_redis = _FakeRedis()

    async def terminal_cache(_session_id):
        return _cached_session(status="submitted", violation_count=5)

    monkeypatch.setattr(service, "get_session_data", terminal_cache)
    monkeypatch.setattr(service, "get_redis", lambda: _fake_get_redis(fake_redis))
    fake_db = _FakeDb(_session_row())

    result = await service.enqueue_violation_event(
        fake_db,
        _violation_log(),
        SimpleNamespace(id=7, username="student01"),
    )

    assert result.status == "ignored"
    assert result.violation_count == 5
    assert fake_db.execute_calls == 0
    assert fake_redis.pending == []


class _ProcessDb:
    def __init__(self):
        self.execute_calls = 0
        self.added = []

    async def execute(self, _stmt):
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _FakeResult(_session_row(violation_count=2))
        return _FakeResult({"id": 10, "exam_id": 99, "violation_count": 3})

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.asyncio
async def test_process_violation_event_writes_log_and_updates_count(monkeypatch) -> None:
    async def count_for_score(*_args, **_kwargs):
        return True, "default"

    monkeypatch.setattr(service, "should_count_violation_for_score", count_for_score)
    db = _ProcessDb()
    event = {
        "event_id": "evt-1",
        "session_id": 10,
        "exam_id": 99,
        "user_id": 7,
        "username": "student01",
        "event_type": "tab_switch",
        "raw_event_type": "tab_switch",
        "event_data": {"source": "apk", "reason": "test"},
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "user_agent": "SXB-Client test",
        "screen_resolution": "1080x1920",
    }

    payload = await service._process_event(db, event)

    assert payload["violation_count"] == 3
    assert payload["counted_for_score"] is True
    assert len(db.added) == 1
    assert db.added[0].event_type == "tab_switch"
