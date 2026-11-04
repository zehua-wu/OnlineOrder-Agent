"""Small deterministic preference retrieval baseline, not a vector database."""

import re

from app.models.memory import LongTermMemory


def select_memories(memories: list[LongTermMemory], query: str, k: int = 8) -> list[LongTermMemory]:
    terms = set(re.findall(r"[a-z]+|[\u4e00-\u9fff]", query.lower()))

    def score(memory):
        text = (memory.key + " " + memory.value).lower()
        safety = any(t in text for t in ("allerg", "restriction", "diet", "过敏", "忌口"))
        overlap = sum(t in text for t in terms)
        return (safety, overlap)

    ranked = sorted(memories, key=score, reverse=True)
    # Include every safety restriction from the bounded backend candidate set,
    # even when this goes over k. A preference must never be an allergy guarantee.
    safety = [m for m in ranked if score(m)[0]]
    return safety + [m for m in ranked if m not in safety][: max(0, k - len(safety))]
