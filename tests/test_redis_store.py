from app.memory.redis_store import RedisSessionStore
from app.models.session import ConversationMessage, ConversationSession


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> None:
        assert ex == 3600
        self.values[key] = value

    async def aclose(self) -> None:
        return None


async def test_redis_session_round_trips_unicode_without_mojibake() -> None:
    redis = FakeRedis()
    store = RedisSessionStore(redis)
    session = ConversationSession(
        session_id="session-1",
        owner_fingerprint="anonymous",
        messages=[
            ConversationMessage(
                role="user",
                content="帮我找15美元以内、不太辣的鸡肉",
            )
        ],
    )

    await store.save(session, 3600)
    stored = redis.values["agent:session:session-1"]
    loaded = await store.get("session-1")

    assert "帮我找" in stored
    assert loaded is not None
    assert loaded.messages[0].content == "帮我找15美元以内、不太辣的鸡肉"
