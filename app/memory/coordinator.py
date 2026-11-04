import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.exceptions import LockError

from app.core.exceptions import HarnessConflictError


class SessionCoordinator:
    """Reference-counted per-user locks; entries disappear when the last waiter exits."""

    def __init__(self) -> None:
        self._locks: dict[str, tuple[asyncio.Lock, int]] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self, key: str) -> AsyncIterator[None]:
        async with self._guard:
            lock, count = self._locks.get(key, (asyncio.Lock(), 0))
            self._locks[key] = (lock, count + 1)
        try:
            async with lock:
                yield
        finally:
            async with self._guard:
                _, count = self._locks[key]
                if count == 1:
                    del self._locks[key]
                else:
                    self._locks[key] = (lock, count - 1)


class RedisSessionCoordinator:
    """Cross-worker user lock. Lease must exceed the entire bounded turn.

    All mutation requests also claim an NX action journal before dispatch; a lost
    lock must never cause a previously dispatched increment to be resent.
    """

    def __init__(self, redis, *, lease_seconds: float = 120, wait_seconds: float = 2) -> None:
        self._redis = redis
        self._lease = lease_seconds
        self._wait = wait_seconds

    @asynccontextmanager
    async def acquire(self, key: str) -> AsyncIterator[None]:
        lock = self._redis.lock(
            f"agent:lock:{key}",
            timeout=self._lease,
            blocking_timeout=self._wait,
            thread_local=False,
        )
        if not await lock.acquire():
            raise HarnessConflictError(
                "TURN_BUSY", "A turn for this user is running; retry later with the same requestId."
            )
        try:
            yield
        finally:
            try:
                await lock.release()
            except LockError as error:
                raise HarnessConflictError(
                    "LOCK_LOST", "The turn lock expired; inspect the action before retrying."
                ) from error
