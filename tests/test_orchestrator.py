from copy import deepcopy

import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.core.exceptions import AgentLoopError, SessionAccessError
from app.llm.base import ModelTurn, ToolCall
from app.memory.coordinator import SessionCoordinator
from app.memory.in_memory import InMemorySessionStore
from app.models.memory import LongTermMemory, MemoryMutation
from app.models.session import ConversationSession, SearchResultReference, SelectedItem
from app.models.tools import SearchFilters
from app.tools.executor import ToolExecutionResult


USER_ID = "11111111-1111-1111-1111-111111111111"
OTHER_USER_ID = "22222222-2222-2222-2222-222222222222"


class FakeModel:
    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = turns
        self.inputs: list[list[object]] = []

    async def respond(self, *, input_items, tools, instructions):
        self.inputs.append(deepcopy(input_items))
        return self.turns.pop(0)


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []
        self.result = ToolExecutionResult(
            output='{"ok":true,"count":1,"items":[{"menuItemName":"Chicken Bowl"}]}'
        )

    async def execute(self, name, arguments, context):
        self.calls.append((name, arguments, context.authorization))
        return self.result


class FakeMemoryStore:
    def __init__(self, memories: list[LongTermMemory] | None = None) -> None:
        self.memories = memories or []
        self.list_calls: list[tuple[str, int]] = []
        self.apply_calls: list[tuple[str, list[MemoryMutation]]] = []

    async def list(self, *, authorization, limit):
        self.list_calls.append((authorization, limit))
        return self.memories

    async def apply(self, *, authorization, mutations):
        self.apply_calls.append((authorization, mutations))
        return self.memories


class FakeMemoryExtractor:
    def __init__(self, mutations: list[MemoryMutation] | None = None) -> None:
        self.mutations = mutations or []
        self.calls: list[tuple[str, list[LongTermMemory]]] = []

    async def extract(self, *, message, existing_memories):
        self.calls.append((message, existing_memories))
        return self.mutations


def make_orchestrator(
    model: FakeModel,
    executor: FakeExecutor,
    store: InMemorySessionStore,
    *,
    user_memory_store=None,
    memory_extractor=None,
):
    return AgentOrchestrator(
        model=model,
        tool_executor=executor,
        session_store=store,
        coordinator=SessionCoordinator(),
        session_ttl_seconds=3600,
        recent_message_limit=12,
        max_tool_steps=5,
        user_memory_store=user_memory_store,
        memory_extractor=memory_extractor,
    )


@pytest.mark.asyncio
async def test_tool_call_round_trip_and_session_history() -> None:
    tool_call = ToolCall(
        call_id="call-1",
        name="search_menu",
        arguments='{"primary_protein":"CHICKEN","max_price":15}',
    )
    model = FakeModel(
        [
            ModelTurn(
                tool_calls=[tool_call],
                output_items=[{"type": "function_call", "call_id": "call-1"}],
            ),
            ModelTurn(text="找到 Chicken Bowl。", output_items=[]),
        ]
    )
    executor = FakeExecutor()
    store = InMemorySessionStore()
    orchestrator = make_orchestrator(model, executor, store)

    response = await orchestrator.chat(
        message="找 15 美元以内的鸡肉",
        session_id=None,
        user_id=USER_ID,
        authorization="Bearer token",
    )

    assert response.answer == "找到 Chicken Bowl。"
    assert response.tool_steps == 1
    assert executor.calls == [
        ("search_menu", tool_call.arguments, "Bearer token")
    ]
    assert model.inputs[1][-1] == {
        "type": "function_call_output",
        "call_id": "call-1",
        "output": '{"ok":true,"count":1,"items":[{"menuItemName":"Chicken Bowl"}]}',
    }

    saved = await store.get(response.session_id)
    assert saved is not None
    assert [message.role for message in saved.messages] == ["user", "assistant"]
    assert "Bearer token" not in saved.model_dump_json()


@pytest.mark.asyncio
async def test_repeated_identical_tool_call_is_stopped() -> None:
    call = ToolCall("call-1", "search_menu", '{"keyword":"ramen"}')
    repeated = ToolCall("call-2", "search_menu", '{ "keyword" : "ramen" }')
    model = FakeModel(
        [
            ModelTurn(tool_calls=[call], output_items=[]),
            ModelTurn(tool_calls=[repeated], output_items=[]),
        ]
    )
    executor = FakeExecutor()
    orchestrator = make_orchestrator(model, executor, InMemorySessionStore())

    with pytest.raises(AgentLoopError, match="repeated"):
        await orchestrator.chat(
            message="ramen",
            session_id=None,
            user_id=USER_ID,
            authorization=None,
        )

    assert len(executor.calls) == 1


@pytest.mark.asyncio
async def test_session_is_bound_to_stable_user_id_across_token_changes() -> None:
    store = InMemorySessionStore()
    first = make_orchestrator(
        FakeModel([ModelTurn(text="hello")]),
        FakeExecutor(),
        store,
    )
    response = await first.chat(
        message="hello",
        session_id=None,
        user_id=USER_ID,
        authorization="Bearer first",
    )

    refreshed = make_orchestrator(
        FakeModel([ModelTurn(text="still the same user")]),
        FakeExecutor(),
        store,
    )
    await refreshed.chat(
        message="continue",
        session_id=response.session_id,
        user_id=USER_ID,
        authorization="Bearer refreshed",
    )

    second = make_orchestrator(
        FakeModel([ModelTurn(text="should not run")]),
        FakeExecutor(),
        store,
    )
    with pytest.raises(SessionAccessError):
        await second.chat(
            message="continue",
            session_id=response.session_id,
            user_id=OTHER_USER_ID,
            authorization="Bearer second",
        )


@pytest.mark.asyncio
async def test_live_legacy_session_is_upgraded_from_token_fingerprint_to_user_id() -> None:
    store = InMemorySessionStore()
    authorization = "Bearer legacy-token"
    legacy = await store.get("missing")
    assert legacy is None

    legacy = ConversationSession(
        session_id="legacy-session",
        owner_fingerprint=AgentOrchestrator._owner_fingerprint(authorization),
    )
    await store.save(legacy, 3600)
    orchestrator = make_orchestrator(
        FakeModel([ModelTurn(text="upgraded")]),
        FakeExecutor(),
        store,
    )

    await orchestrator.chat(
        message="continue",
        session_id="legacy-session",
        user_id=USER_ID,
        authorization=authorization,
    )

    upgraded = await store.get("legacy-session")
    assert upgraded is not None
    assert upgraded.user_id == USER_ID
    assert upgraded.owner_fingerprint is None


@pytest.mark.asyncio
async def test_next_turn_receives_recent_conversation() -> None:
    store = InMemorySessionStore()
    first = make_orchestrator(FakeModel([ModelTurn(text="预算呢？")]), FakeExecutor(), store)
    initial = await first.chat(
        message="我想吃鸡肉",
        session_id=None,
        user_id=USER_ID,
        authorization=None,
    )

    next_model = FakeModel([ModelTurn(text="我来搜索。")])
    second = make_orchestrator(next_model, FakeExecutor(), store)
    await second.chat(
        message="15 美元以内",
        session_id=initial.session_id,
        user_id=USER_ID,
        authorization=None,
    )

    assert next_model.inputs[0] == [
        {"role": "user", "content": "我想吃鸡肉"},
        {"role": "assistant", "content": "预算呢？"},
        {"role": "user", "content": "15 美元以内"},
    ]


@pytest.mark.asyncio
async def test_long_term_memory_is_injected_first_and_updated_after_the_turn() -> None:
    memories = [LongTermMemory(key="spice.preference", value="Prefers mild food")]
    mutation = MemoryMutation(
        operation="UPSERT",
        key="cuisine.preference:thai",
        value="Usually likes Thai food",
    )
    memory_store = FakeMemoryStore(memories)
    extractor = FakeMemoryExtractor([mutation])
    model = FakeModel([ModelTurn(text="I can help with that.")])
    session_store = InMemorySessionStore()
    orchestrator = make_orchestrator(
        model,
        FakeExecutor(),
        session_store,
        user_memory_store=memory_store,
        memory_extractor=extractor,
    )

    response = await orchestrator.chat(
        message="I usually like Thai food.",
        session_id=None,
        user_id=USER_ID,
        authorization="Bearer token",
    )

    assert model.inputs[0][0]["role"] == "developer"
    assert model.inputs[0][0]["content"].startswith("Long-term User Memory")
    assert '"key":"spice.preference"' in model.inputs[0][0]["content"]
    assert model.inputs[0][-1] == {
        "role": "user",
        "content": "I usually like Thai food.",
    }
    assert memory_store.list_calls == [("Bearer token", 50)]
    assert extractor.calls == [("I usually like Thai food.", memories)]
    assert memory_store.apply_calls == [("Bearer token", [mutation])]

    saved = await session_store.get(response.session_id)
    assert saved is not None
    assert saved.user_id == USER_ID
    assert saved.owner_fingerprint is None


@pytest.mark.asyncio
async def test_successful_search_persists_structured_working_state() -> None:
    call = ToolCall(
        "call-1",
        "search_menu",
        '{"keyword":"avocado","start_new_search":false}',
    )
    model = FakeModel(
        [
            ModelTurn(tool_calls=[call]),
            ModelTurn(text="找到一个结果。"),
        ]
    )
    executor = FakeExecutor()
    executor.result = ToolExecutionResult(
        output='{"ok":true}',
        search_state=SearchFilters(
            keyword="avocado",
            primary_protein="CHICKEN",
            max_price=15,
        ),
        search_results=[
            SearchResultReference(
                position=1,
                menu_item_id="item-1",
                name="Chicken Avocado Bowl",
                restaurant_name="Bowl House",
                price=13.99,
            )
        ],
    )
    store = InMemorySessionStore()
    orchestrator = make_orchestrator(model, executor, store)

    response = await orchestrator.chat(
        message="最好有 avocado",
        session_id=None,
        user_id=USER_ID,
        authorization=None,
    )
    saved = await store.get(response.session_id)

    assert saved is not None
    assert saved.state.current_task == "MENU_SEARCH"
    assert saved.state.search.primary_protein == "CHICKEN"
    assert saved.state.search.keyword == "avocado"
    assert saved.state.last_search_results[0].menu_item_id == "item-1"
    assert response.cards[0].menu_item_id == "item-1"
    assert response.total_results == 1
    assert response.has_more is False


@pytest.mark.asyncio
async def test_more_cards_come_from_saved_results_without_model_call() -> None:
    store = InMemorySessionStore()
    first = make_orchestrator(
        FakeModel([ModelTurn(text="Search ready.")]),
        FakeExecutor(),
        store,
    )
    response = await first.chat(
        message="chicken",
        session_id=None,
        user_id=USER_ID,
        authorization="Bearer token",
    )
    saved = await store.get(response.session_id)
    assert saved is not None
    saved.state.last_search_results = [
        SearchResultReference(
            position=position,
            menu_item_id=f"item-{position}",
            name=f"Chicken {position}",
        )
        for position in range(1, 7)
    ]
    await store.save(saved, 3600)

    page = await first.get_search_cards(
        session_id=response.session_id,
        user_id=USER_ID,
        authorization="Bearer token",
        offset=3,
        limit=2,
    )

    assert [card.position for card in page.cards] == [4, 5]
    assert page.next_offset == 5
    assert page.total_results == 6
    assert page.has_more is True


@pytest.mark.asyncio
async def test_working_state_is_injected_before_recent_messages() -> None:
    store = InMemorySessionStore()
    first_model = FakeModel([ModelTurn(text="找到两个结果。")])
    first = make_orchestrator(first_model, FakeExecutor(), store)
    initial = await first.chat(
        message="找鸡肉",
        session_id=None,
        user_id=USER_ID,
        authorization=None,
    )
    saved = await store.get(initial.session_id)
    assert saved is not None
    saved.state.current_task = "MENU_SEARCH"
    saved.state.search = SearchFilters(primary_protein="CHICKEN", max_price=15)
    saved.state.last_search_results = [
        SearchResultReference(position=2, menu_item_id="item-2", name="Chicken Wrap")
    ]
    await store.save(saved, 3600)

    next_model = FakeModel([ModelTurn(text="第二个是 Chicken Wrap。")])
    second = make_orchestrator(next_model, FakeExecutor(), store)
    await second.chat(
        message="第二个不错",
        session_id=initial.session_id,
        user_id=USER_ID,
        authorization=None,
    )

    state_message = next_model.inputs[0][0]
    assert state_message["role"] == "developer"
    assert '"primary_protein":"CHICKEN"' in state_message["content"]
    assert '"menu_item_id":"item-2"' in state_message["content"]


@pytest.mark.asyncio
async def test_selection_tool_persists_selected_item() -> None:
    call = ToolCall(
        "call-select",
        "select_search_result",
        '{"position":2}',
    )
    model = FakeModel(
        [
            ModelTurn(tool_calls=[call]),
            ModelTurn(text="第二个已经选中，但尚未加入购物车。"),
        ]
    )
    executor = FakeExecutor()
    executor.result = ToolExecutionResult(
        output='{"ok":true,"cartChanged":false}',
        selected_item=SelectedItem(
            menu_item_id="item-2",
            name="Avocado Chicken Sushi Wrap",
            restaurant_name="Harbor Bento Lab",
            price=11.75,
        ),
    )
    store = InMemorySessionStore()
    orchestrator = make_orchestrator(model, executor, store)

    response = await orchestrator.chat(
        message="第二个不错",
        session_id=None,
        user_id=USER_ID,
        authorization=None,
    )
    saved = await store.get(response.session_id)

    assert saved is not None
    assert saved.state.selected_item is not None
    assert saved.state.selected_item.menu_item_id == "item-2"
