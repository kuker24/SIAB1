import asyncio
from types import SimpleNamespace

import pytest

from app.core import cache
from app.core import start_db_admission as admission
from app.core.singleflight import KeyedSingleFlight
from app.core.start_db_admission import (
    _admission_limit,
    _parse_admission_limit,
    bind_start_admission,
    configure_start_admission,
    current_start_admission,
    process_admission_snapshot,
    reset_start_admission_for_tests,
    start_db_segment,
)


@pytest.fixture(autouse=True)
def _reset_admission() -> None:
    reset_start_admission_for_tests()
    configure_start_admission(limit=6)
    yield
    reset_start_admission_for_tests()


async def _hold(segment: str, started: asyncio.Event, release: asyncio.Event) -> None:
    async with start_db_segment(segment):
        started.set()
        await release.wait()


@pytest.mark.asyncio
async def test_mixed_segments_share_one_budget() -> None:
    request = SimpleNamespace(state=SimpleNamespace())
    started = [asyncio.Event() for _ in range(30)]
    release = asyncio.Event()
    peaks: list[int] = []

    async def runner(index: int, segment: str) -> None:
        async with bind_start_admission(request):
            await _hold(segment, started[index], release)
            peaks.append(process_admission_snapshot()["peak_holders"])

    segments = (
        ["main"] * 10
        + ["security"] * 10
        + ["questions"] * 8
        + ["integrity"] * 2
    )
    tasks = [
        asyncio.create_task(runner(index, segment))
        for index, segment in enumerate(segments)
    ]
    await asyncio.sleep(0.05)
    snapshot = process_admission_snapshot()
    assert snapshot["holders"] <= 6
    assert snapshot["peak_holders"] <= 6
    release.set()
    await asyncio.gather(*tasks)
    assert max(peaks) <= 6
    assert process_admission_snapshot()["holders"] == 0


@pytest.mark.asyncio
async def test_nested_integrity_does_not_double_acquire() -> None:
    request = SimpleNamespace(state=SimpleNamespace())
    async with bind_start_admission(request):
        async with start_db_segment("main"):
            assert process_admission_snapshot()["holders"] == 1
            async with start_db_segment("integrity"):
                assert process_admission_snapshot()["holders"] == 1
                lease = current_start_admission()
                assert lease is not None
                assert lease.acquisitions[-1]["nested"] is True
                assert lease.acquisitions[-1]["segment"] == "integrity"
        assert process_admission_snapshot()["holders"] == 0


@pytest.mark.asyncio
async def test_unbound_helpers_do_not_consume_start_permits() -> None:
    release = asyncio.Event()
    started = asyncio.Event()
    counter = 0

    async def unbound() -> None:
        nonlocal counter
        async with start_db_segment("security"):
            counter += 1
            if counter == 12:
                started.set()
            await release.wait()

    tasks = [asyncio.create_task(unbound()) for _ in range(12)]
    await asyncio.wait_for(started.wait(), timeout=1)
    assert process_admission_snapshot()["holders"] == 0
    release.set()
    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_singleflight_waiters_do_not_consume_permits() -> None:
    request = SimpleNamespace(state=SimpleNamespace())
    flight = KeyedSingleFlight[str]()
    acquire_count = 0
    loader_started = asyncio.Event()
    release = asyncio.Event()

    async def loader() -> str:
        nonlocal acquire_count
        async with bind_start_admission(request):
            async with start_db_segment("questions"):
                acquire_count += 1
                loader_started.set()
                await release.wait()
                return "payload"

    async def caller() -> str:
        async with bind_start_admission(request):
            return await flight.run("exam:1", loader)

    tasks = [asyncio.create_task(caller()) for _ in range(20)]
    await asyncio.wait_for(loader_started.wait(), timeout=1)
    await asyncio.sleep(0.02)
    assert acquire_count == 1
    assert process_admission_snapshot()["holders"] == 1
    release.set()
    assert await asyncio.gather(*tasks) == ["payload"] * 20
    assert process_admission_snapshot()["holders"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("segment", ["security", "main", "questions", "integrity"])
async def test_segment_exception_restores_permits(segment: str) -> None:
    request = SimpleNamespace(state=SimpleNamespace())

    async with bind_start_admission(request):
        with pytest.raises(RuntimeError):
            async with start_db_segment(segment):
                raise RuntimeError("db failed")
    assert process_admission_snapshot()["holders"] == 0
    assert process_admission_snapshot()["waiters"] == 0

    async with bind_start_admission(request):
        async with start_db_segment(segment):
            assert process_admission_snapshot()["holders"] == 1
    assert process_admission_snapshot()["holders"] == 0


@pytest.mark.asyncio
async def test_cancel_while_holding_restores_permit() -> None:
    request = SimpleNamespace(state=SimpleNamespace())
    started = asyncio.Event()

    async def holder() -> None:
        async with bind_start_admission(request):
            async with start_db_segment("main"):
                started.set()
                await asyncio.sleep(60)

    task = asyncio.create_task(holder())
    await started.wait()
    assert process_admission_snapshot()["holders"] == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process_admission_snapshot()["holders"] == 0


@pytest.mark.asyncio
async def test_cancel_while_waiting_does_not_leak_permit() -> None:
    request = SimpleNamespace(state=SimpleNamespace())
    configure_start_admission(limit=1)
    holders_started = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder() -> None:
        async with bind_start_admission(request):
            async with start_db_segment("main"):
                holders_started.set()
                await release_holder.wait()

    async def waiter() -> None:
        async with bind_start_admission(request):
            async with start_db_segment("security"):
                return

    owner = asyncio.create_task(holder())
    await holders_started.wait()
    waiting = asyncio.create_task(waiter())
    await asyncio.sleep(0.02)
    assert process_admission_snapshot()["waiters"] == 1
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert process_admission_snapshot()["holders"] == 1
    assert process_admission_snapshot()["waiters"] == 0
    release_holder.set()
    await owner
    assert process_admission_snapshot()["holders"] == 0


@pytest.mark.asyncio
async def test_security_cache_fill_uses_gate_only_when_bound(monkeypatch) -> None:
    request = SimpleNamespace(state=SimpleNamespace())
    fills = 0

    class FakeSession:
        async def execute(self, _statement):
            nonlocal fills
            fills += 1
            assert process_admission_snapshot()["holders"] == 1
            return SimpleNamespace(scalar_one_or_none=lambda: None)

    class FakeCtx:
        async def __aenter__(self):
            return FakeSession()

        async def __aexit__(self, *_args):
            return None

    class FakeRedis:
        async def get(self, _key):
            return None

        async def set(self, *_args, **_kwargs):
            return True

    async def fake_get_redis() -> FakeRedis:
        return FakeRedis()

    monkeypatch.setattr(cache, "get_redis", fake_get_redis)
    monkeypatch.setattr(cache, "async_session_read", lambda: FakeCtx())
    monkeypatch.setattr(cache, "_security_cache_fills", KeyedSingleFlight[str]())

    async with bind_start_admission(request):
        assert await cache.is_developer_mode_enabled() is False
    assert fills == 1
    assert process_admission_snapshot()["holders"] == 0
    lease = request.state.start_db_admission
    assert any(item["segment"] == "security" for item in lease["acquisitions"])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 0),
        ("", 0),
        ("   ", 0),
        ("0", 0),
        ("4", 4),
        ("not-a-number", 0),
        ("-3", 0),
        ("4.5", 0),
    ],
)
def test_admission_limit_parsing_is_fail_safe(raw: str | None, expected: int) -> None:
    assert _parse_admission_limit(raw) == expected


def test_missing_env_disables_admission(monkeypatch) -> None:
    monkeypatch.delenv("START_DB_ADMISSION_LIMIT", raising=False)
    reset_start_admission_for_tests()
    assert _admission_limit() == 0


def test_env_zero_disables_admission(monkeypatch) -> None:
    monkeypatch.setenv("START_DB_ADMISSION_LIMIT", "0")
    reset_start_admission_for_tests()
    assert _admission_limit() == 0


def test_env_four_enables_admission(monkeypatch) -> None:
    monkeypatch.setenv("START_DB_ADMISSION_LIMIT", "4")
    reset_start_admission_for_tests()
    assert _admission_limit() == 4


@pytest.mark.asyncio
async def test_disabled_gate_does_not_create_semaphore_or_holders() -> None:
    reset_start_admission_for_tests()
    configure_start_admission(limit=0)
    request = SimpleNamespace(state=SimpleNamespace())
    started = [asyncio.Event() for _ in range(12)]
    release = asyncio.Event()

    async def runner(index: int) -> None:
        async with bind_start_admission(request):
            async with start_db_segment("main"):
                started[index].set()
                await release.wait()

    tasks = [asyncio.create_task(runner(index)) for index in range(12)]
    await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started)), timeout=1)
    snapshot = process_admission_snapshot()
    assert snapshot["limit"] == 0
    assert snapshot["holders"] == 0
    assert admission._gate is not None
    assert admission._gate.semaphore is None
    release.set()
    await asyncio.gather(*tasks)
    assert process_admission_snapshot()["holders"] == 0


@pytest.mark.asyncio
async def test_limit_four_caps_holders() -> None:
    configure_start_admission(limit=4)
    request = SimpleNamespace(state=SimpleNamespace())
    started = [asyncio.Event() for _ in range(8)]
    release = asyncio.Event()

    async def runner(index: int) -> None:
        async with bind_start_admission(request):
            await _hold("main", started[index], release)

    tasks = [asyncio.create_task(runner(index)) for index in range(8)]
    await asyncio.sleep(0.05)
    snapshot = process_admission_snapshot()
    assert snapshot["limit"] == 4
    assert snapshot["holders"] <= 4
    assert snapshot["peak_holders"] <= 4
    release.set()
    await asyncio.gather(*tasks)
    assert process_admission_snapshot()["holders"] == 0


@pytest.mark.asyncio
async def test_gate_recreated_when_limit_changes() -> None:
    configure_start_admission(limit=4)
    request = SimpleNamespace(state=SimpleNamespace())
    async with bind_start_admission(request):
        async with start_db_segment("main"):
            first = process_admission_snapshot()
    configure_start_admission(limit=2)
    async with bind_start_admission(request):
        async with start_db_segment("main"):
            second = process_admission_snapshot()
    assert first["limit"] == 4
    assert second["limit"] == 2
    assert second["pid"] == first["pid"]
