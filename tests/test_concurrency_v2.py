import asyncio

import fakeredis.aioredis
import pytest
from conftest import build_harness

from app.core.exceptions import HarnessConflictError
from app.evaluation.mock_backend import USER_ID
from app.memory.coordinator import RedisSessionCoordinator, SessionCoordinator
from app.memory.redis_store import RedisSessionStore


async def test_local_lock_entries_are_reclaimed_and_cancelled_waiter_cleans_up():
    coordinator = SessionCoordinator()
    async with coordinator.acquire("user"):

        async def wait():
            async with coordinator.acquire("user"):
                raise AssertionError("must not acquire")

        task = asyncio.create_task(wait())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(coordinator._locks) == 1
    assert coordinator._locks == {}


async def test_distributed_coordinators_exclude_other_worker():
    server = fakeredis.FakeServer()
    first = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    second = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    a = RedisSessionCoordinator(first, wait_seconds=0.01)
    b = RedisSessionCoordinator(second, wait_seconds=0.01)
    try:
        async with a.acquire(USER_ID):
            with pytest.raises(HarnessConflictError) as error:
                async with b.acquire(USER_ID):
                    pass
            assert error.value.code == "TURN_BUSY"
        async with b.acquire(USER_ID):
            pass
    finally:
        await first.aclose()
        await second.aclose()


async def test_two_workers_confirm_same_action_only_dispatch_once():
    server = fakeredis.FakeServer()
    redis_a = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    redis_b = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    a = build_harness(
        store=RedisSessionStore(redis_a), coordinator=RedisSessionCoordinator(redis_a)
    )
    b = build_harness(
        store=RedisSessionStore(redis_b),
        coordinator=RedisSessionCoordinator(redis_b),
        backend=a.backend,
    )
    try:
        first = await a.chat("找鸡肉")
        pending = await a.chat("把第一个加入一份", first.session_id)
        action_id = pending.pending_action.action_id
        outputs = await asyncio.gather(
            a.chat("确认", first.session_id, confirm_action_id=action_id),
            b.chat("确认", first.session_id, confirm_action_id=action_id),
        )
        assert all(o.status == "ok" for o in outputs)
        assert a.backend.write_count == 1
        # Simulate worker replacement: journal and session survive on shared Redis.
        replay = await b.chat("确认", first.session_id, confirm_action_id=action_id)
        assert replay.cart["items"][0]["quantity"] == 1
        assert a.backend.write_count == 1
    finally:
        await a.client.aclose()
        await b.client.aclose()
        await redis_a.aclose()
        await redis_b.aclose()
