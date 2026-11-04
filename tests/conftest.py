from dataclasses import dataclass

import httpx
import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.evaluation.mock_backend import USER_ID, DemoBackend
from app.llm.mock import MockOrderingModel
from app.memory.coordinator import SessionCoordinator
from app.memory.in_memory import InMemorySessionStore
from app.tools.executor import ToolExecutor


@dataclass
class Harness:
    agent: AgentOrchestrator
    backend: DemoBackend
    store: InMemorySessionStore
    client: httpx.AsyncClient

    async def chat(self, message, session_id=None, **kwargs):
        return await self.agent.chat(
            message=message,
            session_id=session_id,
            user_id=kwargs.pop("user_id", USER_ID),
            authorization=kwargs.pop("authorization", "Bearer demo-token"),
            **kwargs,
        )


def build_harness(model=None, store=None, coordinator=None, backend=None, **kwargs):
    backend = backend or DemoBackend()
    client = httpx.AsyncClient(
        base_url="http://fixture.test", transport=httpx.MockTransport(backend.handle)
    )
    store = store or InMemorySessionStore()
    agent = AgentOrchestrator(
        model=model or MockOrderingModel(),
        tool_executor=ToolExecutor(OnlineOrderBackendClient(client, read_retries=0)),
        session_store=store,
        coordinator=coordinator or SessionCoordinator(),
        session_ttl_seconds=3600,
        recent_message_limit=kwargs.pop("recent_message_limit", 12),
        max_tool_steps=kwargs.pop("max_tool_steps", 5),
        **kwargs,
    )
    return Harness(agent, backend, store, client)


@pytest.fixture
async def harness():
    value = build_harness()
    yield value
    await value.client.aclose()
