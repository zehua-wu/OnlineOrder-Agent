from __future__ import annotations

from typing import Protocol

from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.models.memory import LongTermMemory, MemoryMutation


class UserMemoryStore(Protocol):
    async def list(
        self,
        *,
        authorization: str,
        limit: int,
    ) -> list[LongTermMemory]: ...

    async def apply(
        self,
        *,
        authorization: str,
        mutations: list[MemoryMutation],
    ) -> list[LongTermMemory]: ...


class BackendUserMemoryStore:
    def __init__(self, backend_client: OnlineOrderBackendClient) -> None:
        self._backend_client = backend_client

    async def list(
        self,
        *,
        authorization: str,
        limit: int,
    ) -> list[LongTermMemory]:
        return await self._backend_client.get_user_memories(
            authorization=authorization,
            limit=limit,
        )

    async def apply(
        self,
        *,
        authorization: str,
        mutations: list[MemoryMutation],
    ) -> list[LongTermMemory]:
        return await self._backend_client.apply_user_memory_mutations(
            authorization=authorization,
            mutations=mutations,
        )


class NoOpUserMemoryStore:
    async def list(
        self,
        *,
        authorization: str,
        limit: int,
    ) -> list[LongTermMemory]:
        return []

    async def apply(
        self,
        *,
        authorization: str,
        mutations: list[MemoryMutation],
    ) -> list[LongTermMemory]:
        return []
