from __future__ import annotations

import asyncio
import os
import re
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar, Token
from typing import Any, AsyncIterator, Optional


START_PATH_RE = re.compile(r"^/api/exams/\d+/start$")
_DEFAULT_LIMIT = 0

_pid: Optional[int] = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_gate: Optional["ProcessAdmissionGate"] = None
_forced_limit: Optional[int] = None
_current_lease: ContextVar[Optional["StartAdmissionLease"]] = ContextVar(
    "siab1_start_db_admission_lease",
    default=None,
)


def is_exam_start_path(path: str) -> bool:
    return bool(START_PATH_RE.match(path or ""))


def _parse_admission_limit(raw: Optional[str]) -> int:
    if raw is None:
        return _DEFAULT_LIMIT
    text = raw.strip()
    if not text:
        return _DEFAULT_LIMIT
    try:
        value = int(text)
    except ValueError:
        return _DEFAULT_LIMIT
    if value < 0:
        return _DEFAULT_LIMIT
    return value


def _admission_limit() -> int:
    if _forced_limit is not None:
        return _parse_admission_limit(str(_forced_limit))
    return _parse_admission_limit(os.getenv("START_DB_ADMISSION_LIMIT"))


class ProcessAdmissionGate:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.semaphore = asyncio.Semaphore(limit) if limit > 0 else None
        self.holders = 0
        self.waiters = 0
        self.peak_holders = 0
        self.peak_waiters = 0


def _get_gate(limit: int) -> ProcessAdmissionGate:
    global _pid, _loop, _gate
    loop = asyncio.get_running_loop()
    pid = os.getpid()
    if _gate is None or _pid != pid or _loop is not loop or _gate.limit != limit:
        _pid = pid
        _loop = loop
        _gate = ProcessAdmissionGate(limit)
    return _gate


def configure_start_admission(*, limit: Optional[int] = None) -> None:
    global _forced_limit, _pid, _loop, _gate
    _forced_limit = limit
    _pid = None
    _loop = None
    _gate = None


def reset_start_admission_for_tests() -> None:
    configure_start_admission(limit=None)
    _current_lease.set(None)


def current_start_admission() -> Optional["StartAdmissionLease"]:
    return _current_lease.get()


def process_admission_snapshot() -> dict[str, Any]:
    limit = _admission_limit()
    gate = _gate
    if gate is None:
        return {
            "pid": os.getpid(),
            "limit": limit,
            "holders": 0,
            "waiters": 0,
            "peak_holders": 0,
            "peak_waiters": 0,
        }
    return {
        "pid": os.getpid(),
        "limit": gate.limit,
        "holders": gate.holders,
        "waiters": gate.waiters,
        "peak_holders": gate.peak_holders,
        "peak_waiters": gate.peak_waiters,
    }


class StartAdmissionLease:
    def __init__(self, request: Any, gate: ProcessAdmissionGate) -> None:
        self.request = request
        self.gate = gate
        self.depth = 0
        self.bind_depth = 1
        self.acquisitions: list[dict[str, Any]] = []

    def publish(self) -> None:
        wait_ms = sum(
            float(item.get("wait_ms") or 0.0)
            for item in self.acquisitions
            if not item.get("nested")
        )
        snapshot = {
            "pid": os.getpid(),
            "limit": self.gate.limit,
            "holders": self.gate.holders,
            "waiters": self.gate.waiters,
            "peak_holders": self.gate.peak_holders,
            "peak_waiters": self.gate.peak_waiters,
            "wait_ms": wait_ms,
            "acquisitions": list(self.acquisitions),
        }
        request = self.request
        if request is not None:
            state = getattr(request, "state", None)
            if state is not None:
                state.start_db_admission = snapshot

    @asynccontextmanager
    async def acquire(self, segment: str) -> AsyncIterator[dict[str, Any]]:
        if self.depth > 0:
            started = time.monotonic()
            started_wall = time.time()
            record = {
                "segment": segment,
                "nested": True,
                "wait_ms": 0.0,
                "hold_ms": 0.0,
                "acquired_wall": started_wall,
                "released_wall": None,
                "holders_at_acquire": self.gate.holders,
                "waiters_at_acquire": self.gate.waiters,
            }
            self.acquisitions.append(record)
            self.depth += 1
            self.publish()
            try:
                yield record
            finally:
                record["hold_ms"] = (time.monotonic() - started) * 1000.0
                record["released_wall"] = time.time()
                self.depth -= 1
                self.publish()
            return

        if self.gate.limit <= 0 or self.gate.semaphore is None:
            started = time.monotonic()
            started_wall = time.time()
            record = {
                "segment": segment,
                "nested": False,
                "wait_ms": 0.0,
                "hold_ms": 0.0,
                "acquired_wall": started_wall,
                "released_wall": None,
                "holders_at_acquire": 0,
                "waiters_at_acquire": 0,
            }
            self.acquisitions.append(record)
            self.depth = 1
            self.publish()
            try:
                yield record
            finally:
                record["hold_ms"] = (time.monotonic() - started) * 1000.0
                record["released_wall"] = time.time()
                self.depth = 0
                self.publish()
            return

        gate = self.gate
        gate.waiters += 1
        gate.peak_waiters = max(gate.peak_waiters, gate.waiters)
        wait_started = time.monotonic()
        try:
            await gate.semaphore.acquire()
        except BaseException:
            gate.waiters = max(0, gate.waiters - 1)
            self.publish()
            raise
        acquired = time.monotonic()
        gate.waiters = max(0, gate.waiters - 1)
        gate.holders += 1
        gate.peak_holders = max(gate.peak_holders, gate.holders)
        record = {
            "segment": segment,
            "nested": False,
            "wait_ms": (acquired - wait_started) * 1000.0,
            "hold_ms": 0.0,
            "acquired_wall": time.time(),
            "released_wall": None,
            "holders_at_acquire": gate.holders,
            "waiters_at_acquire": gate.waiters,
            "peak_holders": gate.peak_holders,
            "peak_waiters": gate.peak_waiters,
        }
        self.acquisitions.append(record)
        self.depth = 1
        self.publish()
        try:
            yield record
        finally:
            record["hold_ms"] = (time.monotonic() - acquired) * 1000.0
            record["released_wall"] = time.time()
            record["peak_holders"] = gate.peak_holders
            record["peak_waiters"] = gate.peak_waiters
            self.depth = 0
            gate.holders = max(0, gate.holders - 1)
            gate.semaphore.release()
            self.publish()


@asynccontextmanager
async def bind_start_admission(request: Any = None) -> AsyncIterator[StartAdmissionLease]:
    existing = _current_lease.get()
    if existing is not None:
        existing.bind_depth += 1
        if request is not None and existing.request is None:
            existing.request = request
        try:
            yield existing
        finally:
            existing.bind_depth -= 1
        return

    gate = _get_gate(_admission_limit())
    lease = StartAdmissionLease(request, gate)
    token: Token = _current_lease.set(lease)
    lease.publish()
    try:
        yield lease
    finally:
        _current_lease.reset(token)


@asynccontextmanager
async def start_db_segment(segment: str) -> AsyncIterator[dict[str, Any]]:
    lease = _current_lease.get()
    if lease is None:
        yield {
            "segment": segment,
            "nested": False,
            "wait_ms": 0.0,
            "hold_ms": 0.0,
            "skipped": True,
        }
        return
    async with lease.acquire(segment) as record:
        yield record
