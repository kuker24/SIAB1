from datetime import datetime, timezone

import pytest

from app.services import answer_runtime_buffer as buffer


def test_runtime_answer_buffer_keys_match_phase6_spec() -> None:
    assert buffer.PENDING_QUEUE_KEY == "runtime:answer_queue:pending"
    assert buffer.PROCESSING_QUEUE_KEY == "runtime:answer_queue:processing"
    assert buffer.session_answers_key(123) == "runtime:session:123:answers"
    assert buffer.session_dirty_questions_key(123) == "runtime:session:123:dirty_questions"
    assert buffer.session_answered_count_key(123) == "runtime:session:123:answered_count"


def test_runtime_answer_buffer_disabled_by_default() -> None:
    assert buffer.is_runtime_answer_buffer_enabled() is False


def _enable_queue(monkeypatch, *, mode="hybrid", enabled=True, percentage=10) -> None:
    monkeypatch.setattr(buffer.settings, "answer_write_mode", mode)
    monkeypatch.setattr(buffer.settings, "answer_queue_enabled", enabled)
    monkeypatch.setattr(buffer.settings, "answer_queue_percentage", percentage)


def test_runtime_answer_buffer_percentage_zero_disables_new_session_routing_only(monkeypatch) -> None:
    _enable_queue(monkeypatch, percentage=0)

    assert buffer.is_runtime_answer_buffer_enabled() is True
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is False


def test_runtime_answer_buffer_global_capability_ignores_percentage_for_flush(monkeypatch) -> None:
    _enable_queue(monkeypatch, mode="hybrid", enabled=True, percentage=0)
    assert buffer.is_runtime_answer_buffer_enabled() is True
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is False

    _enable_queue(monkeypatch, mode="queue", enabled=True, percentage=0)
    assert buffer.is_runtime_answer_buffer_enabled() is True
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is False

    _enable_queue(monkeypatch, mode="direct", enabled=True, percentage=100)
    assert buffer.is_runtime_answer_buffer_enabled() is False
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is False

    _enable_queue(monkeypatch, mode="hybrid", enabled=False, percentage=100)
    assert buffer.is_runtime_answer_buffer_enabled() is False
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is False


def test_runtime_answer_buffer_percentage_hundred_enables_all_eligible_sessions(monkeypatch) -> None:
    _enable_queue(monkeypatch, percentage=100)

    assert buffer.is_runtime_answer_buffer_enabled() is True
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is True
    assert buffer.is_runtime_answer_buffer_enabled_for_session(999, user_id=77, exam_id=88) is True


def test_runtime_answer_buffer_percentage_ten_is_deterministic_subset(monkeypatch) -> None:
    _enable_queue(monkeypatch, percentage=10)

    eligible = [
        session_id
        for session_id in range(1, 1001)
        if buffer.is_runtime_answer_buffer_enabled_for_session(
            session_id,
            user_id=7,
            exam_id=55,
        )
    ]

    assert 50 <= len(eligible) <= 150
    assert len(eligible) < 1000


def test_runtime_answer_buffer_same_session_is_sticky(monkeypatch) -> None:
    _enable_queue(monkeypatch, percentage=10)

    decisions = [
        buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55)
        for _ in range(20)
    ]

    assert len(set(decisions)) == 1


def test_runtime_answer_buffer_different_sessions_distribute_to_different_buckets(monkeypatch) -> None:
    _enable_queue(monkeypatch, percentage=10)

    buckets = {
        buffer._stable_answer_buffer_bucket(
            buffer._answer_buffer_seed(session_id=session_id, user_id=7, exam_id=55)
        )
        for session_id in range(1, 50)
    }

    assert len(buckets) > 20


def test_runtime_answer_buffer_disabled_when_queue_flag_false(monkeypatch) -> None:
    _enable_queue(monkeypatch, enabled=False, percentage=100)

    assert buffer.is_runtime_answer_buffer_enabled() is False
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is False


def test_runtime_answer_buffer_disabled_when_write_mode_direct(monkeypatch) -> None:
    _enable_queue(monkeypatch, mode="direct", percentage=100)

    assert buffer.is_runtime_answer_buffer_enabled() is False
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is False


def test_runtime_answer_buffer_invalid_and_out_of_range_percentage_clamped(monkeypatch) -> None:
    _enable_queue(monkeypatch, percentage="invalid")
    assert buffer._answer_queue_percentage() == 0
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is False

    _enable_queue(monkeypatch, percentage=-5)
    assert buffer._answer_queue_percentage() == 0
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is False

    _enable_queue(monkeypatch, percentage=150)
    assert buffer._answer_queue_percentage() == 100
    assert buffer.is_runtime_answer_buffer_enabled_for_session(123, user_id=7, exam_id=55) is True


class _BufferPipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def hset(self, key, mapping):
        self.ops.append(("hset", key, mapping))
        return self

    def sadd(self, key, *values):
        self.ops.append(("sadd", key, values))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))
        return self

    async def execute(self):
        for op in self.ops:
            if op[0] == "hset":
                _, key, mapping = op
                self.redis.hashes.setdefault(key, {}).update(mapping)
            elif op[0] == "sadd":
                _, key, values = op
                self.redis.sets.setdefault(key, set()).update(values)
        return []


class _BufferRedis:
    def __init__(self):
        self.hashes = {}
        self.sets = {}
        self.values = {}
        self.pending = []

    def pipeline(self):
        return _BufferPipeline(self)

    async def hlen(self, key):
        return len(self.hashes.get(key, {}))

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def rpush(self, key, value):
        self.pending.append((key, value))
        return len(self.pending)

    async def expire(self, key, ttl):
        return True


@pytest.mark.asyncio
async def test_runtime_answer_buffer_answered_count_uses_total_hash_size(monkeypatch) -> None:
    fake_redis = _BufferRedis()

    async def fake_get_redis():
        return fake_redis

    monkeypatch.setattr(buffer, "get_redis", fake_get_redis)

    first_count = await buffer._write_answer_buffer(
        session_id=123,
        user_id=7,
        exam_id=55,
        answers=[{"question_id": 1}, {"question_id": 2}],
    )
    second_count = await buffer._write_answer_buffer(
        session_id=123,
        user_id=7,
        exam_id=55,
        answers=[{"question_id": 3}],
    )

    assert first_count == 2
    assert second_count == 1
    assert fake_redis.values[buffer.session_answered_count_key(123)] == 3
