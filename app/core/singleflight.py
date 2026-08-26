import asyncio
import os
from collections.abc import Awaitable, Callable, Hashable
from typing import Any, Generic, TypeVar


KeyT = TypeVar("KeyT", bound=Hashable)
ValueT = TypeVar("ValueT")


class KeyedSingleFlight(Generic[KeyT]):
    """Deduplicate concurrent coroutine calls for one key in one worker."""

    def __init__(self) -> None:
        self._pid: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._inflight: dict[KeyT, asyncio.Future[Any]] = {}

    def _ensure_worker_context(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        pid = os.getpid()
        if self._pid != pid or self._loop is not loop:
            self._pid = pid
            self._loop = loop
            self._inflight = {}
        return loop

    async def run(
        self,
        key: KeyT,
        loader: Callable[[], Awaitable[ValueT]],
    ) -> ValueT:
        loop = self._ensure_worker_context()
        existing = self._inflight.get(key)
        if existing is not None:
            return await asyncio.shield(existing)

        future: asyncio.Future[ValueT] = loop.create_future()
        self._inflight[key] = future
        try:
            result = await loader()
        except asyncio.CancelledError:
            future.cancel()
            raise
        except BaseException as exc:
            future.set_exception(exc)
            # The loader raises directly; retrieving here avoids an unhandled
            # Future warning when there were no concurrent waiters.
            future.exception()
            raise
        else:
            future.set_result(result)
            return result
        finally:
            if self._inflight.get(key) is future:
                self._inflight.pop(key, None)
