from types import SimpleNamespace

import pytest

from app.memory.extractor import MEMORY_EXTRACTION_PROMPT, OpenAIMemoryExtractor
from app.models.memory import LongTermMemory, MemoryExtractionResult, MemoryMutation


class FakeResponses:
    def __init__(self, parsed: MemoryExtractionResult) -> None:
        self.parsed = parsed
        self.kwargs = None

    async def parse(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(output_parsed=self.parsed)


@pytest.mark.asyncio
async def test_memory_extractor_uses_separate_structured_response_without_tools() -> None:
    parsed = MemoryExtractionResult(
        mutations=[
            MemoryMutation(
                operation="UPSERT",
                key="spice.preference",
                value="Prefers mild food",
            )
        ]
    )
    extractor = OpenAIMemoryExtractor(api_key="test", model="gpt-5-nano")
    fake_responses = FakeResponses(parsed)
    extractor._client = SimpleNamespace(responses=fake_responses)

    mutations = await extractor.extract(
        message="I usually prefer mild food.",
        existing_memories=[
            LongTermMemory(key="cuisine.preference:thai", value="Likes Thai food")
        ],
    )

    assert mutations == parsed.mutations
    assert fake_responses.kwargs["instructions"] == MEMORY_EXTRACTION_PROMPT
    assert fake_responses.kwargs["text_format"] is MemoryExtractionResult
    assert fake_responses.kwargs["store"] is False
    assert "tools" not in fake_responses.kwargs
    assert fake_responses.kwargs["input"][-1] == {
        "role": "user",
        "content": "I usually prefer mild food.",
    }
