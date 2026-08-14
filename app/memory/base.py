from typing import Protocol

from app.models.session import ConversationSession


class SessionStore(Protocol):
    async def get(self, session_id: str) -> ConversationSession | None: ...

    async def save(self, session: ConversationSession, ttl_seconds: int) -> None: ...

    async def close(self) -> None: ...

