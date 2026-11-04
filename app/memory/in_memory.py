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

    async def get_record(self, key: str) -> str | None:
        async with self._lock:
            value = self._sessions.get("record:" + key)
            if value is None:
                return None
            if value[0] <= time.monotonic():
                del self._sessions["record:" + key]
                return None
            return value[1]

    async def put_record(self, key: str, value: str, ttl_seconds: int, *, nx: bool = False) -> bool:
        async with self._lock:
            record_key = "record:" + key
            previous = self._sessions.get(record_key)
            if nx and previous and previous[0] > time.monotonic():
                return False
            self._sessions[record_key] = (time.monotonic() + ttl_seconds, value)
            # Amortized cleanup so expired sessions do not accumulate forever.
            for old_key, (expiry, _) in list(self._sessions.items()):
                if expiry <= time.monotonic():
                    del self._sessions[old_key]
            return True

    async def delete_record(self, key: str) -> None:
        async with self._lock:
            self._sessions.pop("record:" + key, None)

    async def close(self) -> None:
        return None
