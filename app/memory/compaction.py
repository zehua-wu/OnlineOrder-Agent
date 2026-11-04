"""Bounded, deterministic episodic memory; never synthesizes business facts."""

import json

from app.models.session import ConversationSession


def compact_session(session: ConversationSession, recent_limit: int) -> None:
    # Retain whole user/assistant pairs. Store a bounded tail of older user quotes,
    # not an LLM-authored narrative that could turn guesses into authoritative facts.
    limit = max(2, recent_limit - recent_limit % 2)
    removed = session.messages[:-limit]
    if removed:
        try:
            episodes = json.loads(session.summary or "[]")
            if not isinstance(episodes, list):
                episodes = []
        except ValueError:
            episodes = []
        episodes.extend(m.content[:180] for m in removed if m.role == "user")
        session.summary = json.dumps(episodes[-6:], ensure_ascii=False)
        session.messages = session.messages[-limit:]
