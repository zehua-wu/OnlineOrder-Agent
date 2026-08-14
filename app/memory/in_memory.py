import asyncio
import time

from app.models.session import ConversationSession


class InMemorySessionStore:
    """Development/test store. State is local to one process and is not durable."""

    def __init__(self) -> None:
        self._sessions: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    async def get(self, session_id: str) -> ConversationSession | None:
        async with self._lock:
            value = self._sessions.get(session_id)
            if value is None:
                return None
            expires_at, serialized = value
            if expires_at <= time.monotonic():
                self._sessions.pop(session_id, None)
                return None
            return ConversationSession.model_validate_json(serialized)

    async def save(self, session: ConversationSession, ttl_seconds: int) -> None:
        async with self._lock:
            self._sessions[session.session_id] = (
                time.monotonic() + ttl_seconds,
                session.model_dump_json(),
            )

    async def close(self) -> None:
        return None

