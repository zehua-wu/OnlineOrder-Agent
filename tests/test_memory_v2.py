import json

from conftest import build_harness

from app.llm.base import ModelTurn, ToolCall
from app.memory.extractor import ToolMemoryExtractor
from app.memory.retrieval import select_memories
from app.models.memory import LongTermMemory


class ExtractionModel:
    def __init__(self, mutations):
        self.mutations = mutations
        self.calls = 0

    async def respond(self, **kwargs):
        self.calls += 1
        return ModelTurn(
            tool_calls=[
                ToolCall("extract", "record_memories", json.dumps({"mutations": self.mutations}))
            ]
        )


async def test_durable_memory_gate_and_quote_validation():
    model = ExtractionModel(
        [
            {
                "operation": "UPSERT",
                "key": "spice.preference",
                "value": "Prefers mild food",
                "evidence": "usually prefer mild",
            },
            {
                "operation": "UPSERT",
                "key": "diet.vegan",
                "value": "Is vegan",
                "evidence": "I am vegan",
            },
            {
                "operation": "UPSERT",
                "key": "api_key",
                "value": "secret",
                "evidence": "usually prefer mild",
            },
        ]
    )
    extractor = ToolMemoryExtractor(model)
    assert await extractor.extract(message="find chicken under $15", existing_memories=[]) == []
    assert model.calls == 0
    accepted = await extractor.extract(message="I usually prefer mild food", existing_memories=[])
    assert [m.key for m in accepted] == ["spice.preference"]


async def test_delete_requires_existing_key_and_explicit_message():
    model = ExtractionModel(
        [
            {
                "operation": "DELETE",
                "key": "spice.preference",
                "value": None,
                "evidence": "忘记我的口味",
            }
        ]
    )
    extractor = ToolMemoryExtractor(model)
    assert await extractor.extract(message="忘记我的口味", existing_memories=[]) == []
    result = await extractor.extract(
        message="忘记我的口味",
        existing_memories=[LongTermMemory(key="spice.preference", value="Mild")],
    )
    assert result[0].operation == "DELETE"


def test_memory_retrieval_keeps_safety_restrictions_and_relevant_preferences():
    memories = [
        LongTermMemory(key=f"ingredient.like:{n}", value=f"Likes ingredient {n}") for n in range(20)
    ]
    memories += [
        LongTermMemory(key="allergy.peanuts", value="Peanut allergy"),
        LongTermMemory(key="cuisine.thai", value="Likes Thai food"),
    ]
    retrieved = select_memories(memories, "Thai food", k=3)
    assert "allergy.peanuts" in {m.key for m in retrieved}
    assert "cuisine.thai" in {m.key for m in retrieved}
    assert len(retrieved) == 3


async def test_memory_failure_does_not_abort_ordering_turn():
    class BrokenMemory:
        async def list(self, **kwargs):
            raise RuntimeError("Must not leak sensitive provider text")

        async def apply(self, **kwargs):
            raise RuntimeError("Must not leak")

    h = build_harness(user_memory_store=BrokenMemory())
    try:
        response = await h.chat("找鸡肉")
        assert response.status == "ok"
        assert response.cards
    finally:
        await h.client.aclose()
