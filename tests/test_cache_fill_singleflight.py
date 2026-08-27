import asyncio
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from app.core import cache
from app.core.cache_manager import cache_manager
from app.core.singleflight import KeyedSingleFlight
from app.middleware import seb_validation
from app.services import exam_service as exam_service_module
from app.services.exam_service import ExamService
from app.utils import apk_validation


class _ScalarResult:
    def __init__(self, value: Any):
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _ScalarsResult:
    def __init__(self, values: list[Any]):
        self._values = values

    def scalars(self) -> "_ScalarsResult":
        return self

    def all(self) -> list[Any]:
        return self._values


class _SessionContext:
    def __init__(self, session: Any):
        self._session = session

    async def __aenter__(self) -> Any:
        return self._session

    async def __aexit__(self, *_args: Any) -> None:
        return None


class _MissBarrierRedis:
    def __init__(self, callers: int):
        self.callers = callers
        self.get_calls = 0
        self._all_gets_started = asyncio.Event()
        self.values: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        self.get_calls += 1
        if self.get_calls >= self.callers:
            self._all_gets_started.set()
        await self._all_gets_started.wait()
        return self.values.get(key)

    async def set(self, key: str, value: Any, **_kwargs: Any) -> bool:
        self.values[key] = value
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("function_name", "expected_result"),
    [
        ("is_developer_mode_enabled", False),
        ("is_freeze_mode_enabled", False),
        ("get_allowed_signatures", []),
    ],
)
async def test_security_cache_cold_burst_executes_one_db_fill(
    monkeypatch,
    function_name: str,
    expected_result: Any,
) -> None:
    callers = 20
    redis = _MissBarrierRedis(callers)
    loader_calls = 0
    setting = SimpleNamespace(
        allow_browser_testing=False,
        freeze_mode=False,
        allowed_signatures=None,
    )

    class FakeSession:
        async def execute(self, _statement: Any) -> _ScalarResult:
            nonlocal loader_calls
            loader_calls += 1
            await asyncio.sleep(0.02)
            return _ScalarResult(setting)

    async def fake_get_redis() -> _MissBarrierRedis:
        return redis

    monkeypatch.setattr(cache, "get_redis", fake_get_redis)
    monkeypatch.setattr(
        cache,
        "async_session_read",
        lambda: _SessionContext(FakeSession()),
    )

    cache_function: Callable[[], Any] = getattr(cache, function_name)
    results = await asyncio.gather(*(cache_function() for _ in range(callers)))

    assert results == [expected_result] * callers
    assert loader_calls == 1


@pytest.mark.asyncio
async def test_question_payload_cold_burst_executes_one_db_fill(monkeypatch) -> None:
    callers = 20
    redis = _MissBarrierRedis(callers)
    loader_calls = 0
    cache_writes = 0
    question = SimpleNamespace(
        id=11,
        question_text="Question",
        stimulus=None,
        question_type="multiple_choice",
        pgk_type=None,
        points=1,
        order_index=1,
        image_url=None,
        video_url=None,
        audio_url=None,
        question_settings={},
        options=[],
    )

    class FakeDb:
        async def execute(self, _statement: Any) -> _ScalarsResult:
            nonlocal loader_calls
            loader_calls += 1
            await asyncio.sleep(0.02)
            return _ScalarsResult([question])

    async def fake_cache_get(key: str) -> Any:
        return await redis.get(key)

    async def fake_cache_set(key: str, value: str, ttl: int) -> bool:
        nonlocal cache_writes
        cache_writes += 1
        redis.values[key] = value
        return True

    monkeypatch.setattr(cache_manager, "get", fake_cache_get)
    monkeypatch.setattr(cache_manager, "set", fake_cache_set)
    monkeypatch.setattr(
        exam_service_module,
        "async_session_read",
        lambda: _SessionContext(FakeDb()),
    )

    services = [ExamService(FakeDb()) for _ in range(callers)]
    results = await asyncio.gather(
        *(service.get_questions_payload(91) for service in services)
    )

    assert all(result[0]["id"] == 11 for result in results)
    assert loader_calls == 1
    assert cache_writes == 1

    redis.values.clear()
    second_generation = await asyncio.gather(
        *(service.get_questions_payload(91) for service in services)
    )

    assert all(result[0]["id"] == 11 for result in second_generation)
    assert loader_calls == 2
    assert cache_writes == 2


@pytest.mark.asyncio
async def test_allow_mobile_local_cache_already_deduplicates_cold_fill(
    monkeypatch,
) -> None:
    loader_calls = 0

    class FakeSession:
        async def execute(self, _statement: Any) -> _ScalarResult:
            nonlocal loader_calls
            loader_calls += 1
            await asyncio.sleep(0.02)
            return _ScalarResult(True)

    monkeypatch.setattr(
        "app.database.async_session_read",
        lambda: _SessionContext(FakeSession()),
    )
    monkeypatch.setattr(
        seb_validation,
        "_allow_mobile_cache",
        {"expires_at": 0.0, "allow_mobile": True},
    )
    monkeypatch.setattr(seb_validation, "_allow_mobile_cache_lock", asyncio.Lock())

    results = await asyncio.gather(
        *(seb_validation._get_allow_mobile_apps_cached() for _ in range(20))
    )

    assert results == [True] * 20
    assert loader_calls == 1


@pytest.mark.asyncio
async def test_apk_settings_local_cache_already_deduplicates_cold_fill(
    monkeypatch,
) -> None:
    loader_calls = 0
    setting = SimpleNamespace(
        minimum_apk_token=None,
        token_validation_bypass=False,
    )

    class FakeSession:
        async def execute(self, _statement: Any) -> _ScalarResult:
            nonlocal loader_calls
            loader_calls += 1
            await asyncio.sleep(0.02)
            return _ScalarResult(setting)

    monkeypatch.setattr(
        apk_validation,
        "async_session_read",
        lambda: _SessionContext(FakeSession()),
    )
    monkeypatch.setattr(
        apk_validation,
        "_settings_cache",
        {
            "expires_at": 0.0,
            "minimum_token": None,
            "allowed_tokens": [],
            "token_profiles": {
                "stable": None,
                "new_update": None,
                "tokens": [],
                "labels_by_token": {},
            },
            "token_validation_bypass": False,
            "settings_fetch_error": False,
        },
    )
    monkeypatch.setattr(apk_validation, "_settings_cache_lock", asyncio.Lock())

    results = await asyncio.gather(
        *(apk_validation._get_settings_cache() for _ in range(20))
    )

    assert all(result["settings_fetch_error"] is False for result in results)
    assert loader_calls == 1


@pytest.mark.asyncio
async def test_singleflight_different_keys_do_not_block_each_other() -> None:
    singleflight = KeyedSingleFlight[str]()
    both_started = asyncio.Event()
    release = asyncio.Event()
    started: set[str] = set()

    async def load(key: str) -> str:
        started.add(key)
        if len(started) == 2:
            both_started.set()
        await release.wait()
        return key

    tasks = [
        asyncio.create_task(singleflight.run(key, lambda key=key: load(key)))
        for key in ("exam-a", "exam-b")
    ]
    await asyncio.wait_for(both_started.wait(), timeout=1)
    release.set()

    assert await asyncio.gather(*tasks) == ["exam-a", "exam-b"]


@pytest.mark.asyncio
async def test_singleflight_loader_exception_reaches_waiters_and_allows_retry() -> None:
    singleflight = KeyedSingleFlight[str]()
    loader_started = asyncio.Event()
    release = asyncio.Event()
    loader_calls = 0

    async def failing_loader() -> str:
        nonlocal loader_calls
        loader_calls += 1
        loader_started.set()
        await release.wait()
        raise RuntimeError("loader failed")

    tasks = [
        asyncio.create_task(singleflight.run("key", failing_loader))
        for _ in range(20)
    ]
    await loader_started.wait()
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert loader_calls == 1
    assert all(isinstance(result, RuntimeError) for result in results)
    assert await singleflight.run("key", lambda: _return_value("retry")) == "retry"


@pytest.mark.asyncio
async def test_singleflight_loader_cancellation_clears_marker_for_retry() -> None:
    singleflight = KeyedSingleFlight[str]()
    loader_started = asyncio.Event()
    release = asyncio.Event()
    loader_calls = 0

    async def cancelled_loader() -> str:
        nonlocal loader_calls
        loader_calls += 1
        loader_started.set()
        await release.wait()
        raise asyncio.CancelledError

    tasks = [
        asyncio.create_task(singleflight.run("key", cancelled_loader))
        for _ in range(20)
    ]
    await loader_started.wait()
    await asyncio.sleep(0)
    release.set()
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert loader_calls == 1
    assert all(isinstance(result, asyncio.CancelledError) for result in results)
    assert await singleflight.run("key", lambda: _return_value("retry")) == "retry"


@pytest.mark.asyncio
async def test_singleflight_waiter_cancellation_does_not_cancel_loader() -> None:
    singleflight = KeyedSingleFlight[str]()
    loader_started = asyncio.Event()
    release = asyncio.Event()

    async def loader() -> str:
        loader_started.set()
        await release.wait()
        return "value"

    owner = asyncio.create_task(singleflight.run("key", loader))
    await loader_started.wait()
    waiter = asyncio.create_task(singleflight.run("key", loader))
    await asyncio.sleep(0)
    waiter.cancel()

    with pytest.raises(asyncio.CancelledError):
        await waiter
    release.set()
    assert await owner == "value"


@pytest.mark.asyncio
async def test_singleflight_waiter_timeout_does_not_poison_loader() -> None:
    singleflight = KeyedSingleFlight[str]()
    loader_started = asyncio.Event()
    release = asyncio.Event()

    async def loader() -> str:
        loader_started.set()
        await release.wait()
        return "value"

    owner = asyncio.create_task(singleflight.run("key", loader))
    await loader_started.wait()

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(singleflight.run("key", loader), timeout=0.01)

    release.set()
    assert await owner == "value"
    assert await singleflight.run("key", lambda: _return_value("retry")) == "retry"


async def _return_value(value: str) -> str:
    return value
