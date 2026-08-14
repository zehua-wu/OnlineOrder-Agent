from redis.asyncio import Redis

from app.models.session import ConversationSession


class RedisSessionStore:
    KEY_PREFIX = "agent:session"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, session_id: str) -> ConversationSession | None:
        value = await self._redis.get(self._key(session_id))
        if value is None:
            return None
        return ConversationSession.model_validate_json(value)

    async def save(self, session: ConversationSession, ttl_seconds: int) -> None:
        await self._redis.set(
            self._key(session.session_id),
            session.model_dump_json(),
            ex=ttl_seconds,
        )

    async def close(self) -> None:
        await self._redis.aclose()

    @classmethod
    def _key(cls, session_id: str) -> str:
        return f"{cls.KEY_PREFIX}:{session_id}"

