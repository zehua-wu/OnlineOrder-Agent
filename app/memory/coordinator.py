import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class SessionCoordinator:
    """Serializes turns for one session inside a single service process."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, session_id: str) -> AsyncIterator[None]:
        async with self._guard:
            lock = self._locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            yield

