"""Replay and write-ahead records use the same backend as sessions.

Keys include the authenticated stable user ID, never a model-provided identity.
"""

from app.memory.base import SessionStore
from app.models.harness import ActionRecord, RequestRecord


class HarnessJournal:
    def __init__(self, store: SessionStore, ttl_seconds: int) -> None:
        self.store = store
        self.ttl = ttl_seconds

    async def request(self, user: str, request: str) -> RequestRecord | None:
        raw = await self.store.get_record(f"request:{user}:{request}")
        return RequestRecord.model_validate_json(raw) if raw else None

    async def save_request(
        self, user: str, request: str, record: RequestRecord, *, nx: bool = False
    ) -> bool:
        return await self.store.put_record(
            f"request:{user}:{request}", record.model_dump_json(), self.ttl, nx=nx
        )

    async def action(self, user: str, action: str) -> ActionRecord | None:
        raw = await self.store.get_record(f"action:{user}:{action}")
        return ActionRecord.model_validate_json(raw) if raw else None

    async def save_action(self, user: str, record: ActionRecord, *, nx: bool = False) -> bool:
        return await self.store.put_record(
            f"action:{user}:{record.action.action_id}", record.model_dump_json(), self.ttl, nx=nx
        )

    async def barrier(self, user: str) -> str | None:
        return await self.store.get_record(f"uncertain:{user}")

    async def block(self, user: str, action_id: str) -> None:
        await self.store.put_record(f"uncertain:{user}", action_id, self.ttl)

    async def unblock(self, user: str) -> None:
        await self.store.delete_record(f"uncertain:{user}")
