import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from conftest import build_harness

from app.core.exceptions import HarnessConflictError, SessionAccessError, SessionNotFoundError
from app.evaluation.mock_backend import ITEM_1, ITEM_2, OTHER_USER_ID, USER_ID
from app.llm.base import ModelTurn, ToolCall
from app.models.harness import RequestRecord
from app.models.tools import SearchFilters
from app.tools.definitions import AGENT_TOOLS
from app.tools.executor import ToolContext


class SequenceModel:
    def __init__(self, turns):
        self.turns = list(turns)
        self.inputs = []

    async def respond(self, **kwargs):
        self.inputs.append(kwargs["input_items"].copy())
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def tool(name, args):
    return ModelTurn(tool_calls=[ToolCall(str(uuid4()), name, json.dumps(args))])


async def prepare(harness):
    search = await harness.chat("找15美元以内不太辣的鸡肉")
    pending = await harness.chat("把第二个加入两份", search.session_id)
    assert pending.pending_action
    return pending


async def test_full_search_refine_select_confirm_cart(harness):
    first = await harness.chat("找15美元以内不太辣的鸡肉")
    refined = await harness.chat("最好有avocado", first.session_id)
    assert [c.menu_item_id for c in refined.cards] == [ITEM_1, ITEM_2]
    chosen = await harness.chat("第二个不错", first.session_id)
    assert harness.backend.write_count == 0
    pending = await harness.chat("把第二个加入两份", chosen.session_id)
    assert pending.pending_action.quantity == 2
    assert harness.backend.write_count == 0
    confirmed = await harness.chat(
        "确认", pending.session_id, confirm_action_id=pending.pending_action.action_id
    )
    assert confirmed.status == "ok"
    assert confirmed.cart["items"][0]["quantity"] == 2
    assert confirmed.metrics.model_calls == 0
    cart = await harness.chat("查看购物车", pending.session_id)
    assert cart.cart["totalAmount"] == 28
    saved = await harness.store.get(first.session_id)
    assert saved.state.search.max_price == 15
    assert saved.state.search.max_spicy_level == 1
    assert saved.state.search.primary_protein == "CHICKEN"
    assert saved.state.phase == "CHAT"
    assert saved.turn_count == 6
    assert "Bearer" not in saved.model_dump_json()


async def test_request_replay_without_initial_session_id(harness):
    request_id = str(uuid4())
    first = await harness.chat("找鸡肉", request_id=request_id)
    calls = len(harness.backend.calls)
    second = await harness.chat("找鸡肉", request_id=request_id)
    assert first == second
    assert len(harness.backend.calls) == calls
    with pytest.raises(HarnessConflictError, match="different input"):
        await harness.chat("找素食", request_id=request_id)


async def test_interrupted_request_never_reruns_implicitly(harness):
    request = str(uuid4())
    # A process died after reserving a request. Use its actual fingerprint.
    import hashlib

    fingerprint = hashlib.sha256(
        json.dumps([None, "hello", None], ensure_ascii=False).encode()
    ).hexdigest()
    await harness.agent._journal.save_request(
        USER_ID, request, RequestRecord(fingerprint=fingerprint, session_id=str(uuid4()))
    )
    with pytest.raises(HarnessConflictError) as error:
        await harness.chat("hello", request_id=request)
    assert error.value.code == "REQUEST_INTERRUPTED"


async def test_confirm_action_and_http_request_are_independently_idempotent(harness):
    pending = await prepare(harness)
    action = pending.pending_action.action_id
    request = str(uuid4())
    first = await harness.chat(
        "确认", pending.session_id, request_id=request, confirm_action_id=action
    )
    replay = await harness.chat(
        "确认", pending.session_id, request_id=request, confirm_action_id=action
    )
    again = await harness.chat("确认", pending.session_id, confirm_action_id=action)
    assert replay == first
    assert again.cart == first.cart
    assert harness.backend.write_count == 1


@pytest.mark.parametrize("fault", ["timeout_after_commit", "500_after_commit", "invalid_json"])
async def test_unknown_write_blocks_new_writes_until_explicit_review(harness, fault):
    pending = await prepare(harness)
    action_id = pending.pending_action.action_id
    harness.backend.next_cart_write_error = fault
    unknown = await harness.chat("确认", pending.session_id)
    assert unknown.status == "degraded"
    assert unknown.error_code == "WRITE_OUTCOME_UNKNOWN"
    assert harness.backend.write_count == 1
    record = await harness.agent.get_action(user_id=USER_ID, action_id=action_id)
    assert record.status == "UNKNOWN"
    again = await harness.chat("确认", pending.session_id, confirm_action_id=action_id)
    assert again.status == "degraded"
    staged = await harness.chat("把第一个加入一份", pending.session_id)
    blocked = await harness.chat("确认", staged.session_id)
    assert blocked.error_code == "UNRESOLVED_CART_WRITE"
    assert harness.backend.write_count == 1
    live = await harness.chat("查看购物车", pending.session_id)
    assert live.cart["items"][0]["quantity"] == 2
    reviewed = await harness.agent.acknowledge_action(
        user_id=USER_ID, action_id=action_id, authorization="Bearer demo-token"
    )
    assert reviewed.status == "ACKNOWLEDGED"
    resumed = await harness.chat("确认", staged.session_id)
    assert resumed.status == "ok"
    assert harness.backend.write_count == 2


async def test_definite_rejection_does_not_retry(harness):
    pending = await prepare(harness)
    harness.backend.next_cart_write_error = "conflict"
    response = await harness.chat("确认", pending.session_id)
    assert response.error_code == "CONFLICT"
    assert harness.backend.write_count == 1
    action = await harness.agent.get_action(
        user_id=USER_ID, action_id=pending.pending_action.action_id
    )
    assert action.status == "FAILED"
    assert await harness.agent._journal.barrier(USER_ID) is None


async def test_cancel_and_expired_pending_action_never_write(harness):
    pending = await prepare(harness)
    await harness.chat("取消", pending.session_id)
    assert (await harness.store.get(pending.session_id)).state.pending_action is None
    pending = await harness.chat("把第一个加入一份", pending.session_id)
    saved = await harness.store.get(pending.session_id)
    saved.state.pending_action.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await harness.store.save(saved, 3600)
    with pytest.raises(HarnessConflictError) as error:
        await harness.chat("确认", pending.session_id)
    assert error.value.code == "ACTION_EXPIRED"
    assert harness.backend.write_count == 0


async def test_wrong_confirmation_id_does_not_write(harness):
    pending = await prepare(harness)
    with pytest.raises(HarnessConflictError) as error:
        await harness.chat("确认", pending.session_id, confirm_action_id=str(uuid4()))
    assert error.value.code == "ACTION_MISMATCH"
    assert harness.backend.write_count == 0


async def test_expired_session_is_not_silently_recreated(harness):
    with pytest.raises(SessionNotFoundError):
        await harness.chat("继续", str(uuid4()))


async def test_cross_user_session_and_action_are_isolated(harness):
    pending = await prepare(harness)
    await harness.chat("确认", pending.session_id)
    with pytest.raises(SessionAccessError):
        await harness.chat("继续", pending.session_id, user_id=OTHER_USER_ID)
    with pytest.raises(SessionNotFoundError):
        await harness.agent.get_action(
            user_id=OTHER_USER_ID, action_id=pending.pending_action.action_id
        )


async def test_stale_results_require_refresh(harness):
    first = await harness.chat("找鸡肉")
    saved = await harness.store.get(first.session_id)
    saved.state.results_updated_at = datetime.now(UTC) - timedelta(hours=1)
    await harness.store.save(saved, 3600)
    response = await harness.chat("把第一个加入一份", first.session_id)
    assert response.pending_action is None
    assert response.metrics.tools[0].code == "STALE_RESULT"
    assert harness.backend.write_count == 0


async def test_search_or_selection_invalidates_prior_confirmation(harness):
    pending = await prepare(harness)
    await harness.chat("第一个不错", pending.session_id)
    with pytest.raises(HarnessConflictError):
        await harness.chat(
            "确认", pending.session_id, confirm_action_id=pending.pending_action.action_id
        )
    assert harness.backend.write_count == 0


async def test_model_cannot_expose_a_commit_tool():
    names = {t["name"] for t in AGENT_TOOLS}
    assert "add_to_cart" in names
    assert "confirm_add_to_cart" not in names
    assert "commit_add_to_cart" not in names


@pytest.mark.parametrize(
    "arguments",
    [
        "not json",
        "[]",
        '{"quantity":true}',
        '{"quantity":"2"}',
        '{"quantity":1.5}',
        '{"quantity":0}',
        '{"quantity":100}',
        '{"quantity":1,"menu_item_id":"forged"}',
        '{"quantity":1,"confirmed":true}',
        '{"position":true,"quantity":1}',
    ],
)
async def test_cart_argument_validation_rejects_coercion_and_invented_fields(harness, arguments):
    response = await harness.agent._tool_executor.execute(
        "add_to_cart",
        arguments,
        ToolContext(authorization="Bearer demo-token", current_search=SearchFilters()),
    )
    assert json.loads(response.output)["error"]["code"] == "INVALID_TOOL_ARGUMENTS"
    assert harness.backend.calls == []


async def test_menu_browse_uses_actual_endpoint_and_normalizes_reference(harness):
    response = await harness.chat("看看菜单")
    assert [t.name for t in response.metrics.tools] == ["list_restaurants", "get_menu"]
    assert response.cards[0].menu_item_id == ITEM_1
    assert any(path.endswith("/menu") for _, path, _ in harness.backend.calls)
    staged = await harness.chat("把第一个加入一份", response.session_id)
    assert staged.pending_action.menu_item_id == ITEM_1


async def test_unknown_restaurant_is_not_requested(harness):
    response = await harness.agent._tool_executor.execute(
        "get_menu",
        json.dumps({"restaurant_id": str(uuid4())}),
        ToolContext(authorization=None, current_search=SearchFilters()),
    )
    assert json.loads(response.output)["error"]["code"] == "UNKNOWN_RESTAURANT"
    assert harness.backend.calls == []


async def test_timeout_after_backend_dispatch_persists_uncertainty(harness):
    pending = await prepare(harness)
    original = harness.agent._tool_executor.commit_add

    async def slow_commit(*args, **kwargs):
        result = await original(*args, **kwargs)
        await asyncio.sleep(1)
        return result

    harness.agent._tool_executor.commit_add = slow_commit
    harness.agent._turn_timeout = 0.01
    response = await harness.chat("确认", pending.session_id)
    assert response.error_code == "TURN_TIMEOUT"
    record = await harness.agent.get_action(
        user_id=USER_ID, action_id=pending.pending_action.action_id
    )
    assert record.status == "UNKNOWN"
    assert harness.backend.write_count == 1


async def test_failure_saving_success_still_prevents_second_dispatch(harness):
    pending = await prepare(harness)
    original = harness.store.put_record
    from redis.exceptions import ConnectionError

    async def fail_success(key, value, ttl_seconds, **kwargs):
        if key.startswith("action:") and '"status":"SUCCEEDED"' in value:
            raise ConnectionError("Simulated Redis loss after backend commit")
        return await original(key, value, ttl_seconds, **kwargs)

    harness.store.put_record = fail_success
    with pytest.raises(ConnectionError):
        await harness.chat("确认", pending.session_id)
    harness.store.put_record = original
    response = await harness.chat(
        "确认", pending.session_id, confirm_action_id=pending.pending_action.action_id
    )
    assert response.error_code == "ACTION_ALREADY_DISPATCHED"
    assert harness.backend.write_count == 1


async def test_model_failure_after_search_keeps_cards_and_state():
    from app.core.exceptions import AgentLoopError

    h = build_harness(
        model=SequenceModel(
            [tool("search_menu", {"primary_protein": "CHICKEN"}), AgentLoopError("empty")]
        )
    )
    try:
        result = await h.chat("找鸡肉")
        assert result.status == "degraded"
        assert len(result.cards) == 2
        assert (await h.store.get(result.session_id)).state.last_search_results
    finally:
        await h.client.aclose()


async def test_step_budget_and_timeout_return_bounded_response():
    h = build_harness(
        model=SequenceModel([tool("get_cart", {}), tool("list_restaurants", {})]), max_tool_steps=1
    )
    try:
        result = await h.chat("查看购物车")
        assert result.error_code == "AGENT_LOOP_STOPPED"
        assert result.tool_steps == 1
    finally:
        await h.client.aclose()


async def test_recent_memory_compacts_whole_turns_and_only_user_quotes():
    h = build_harness(recent_message_limit=4)
    try:
        session_id = None
        for n in range(10):
            result = await h.chat(f"hello {n}", session_id)
            session_id = result.session_id
        saved = await h.store.get(session_id)
        assert len(saved.messages) == 4
        assert [m.role for m in saved.messages] == ["user", "assistant", "user", "assistant"]
        assert json.loads(saved.summary) == [f"hello {n}" for n in range(2, 8)]
        assert saved.turn_count == 10
    finally:
        await h.client.aclose()


async def test_confirmation_checks_combined_cart_quantity_against_snapshot(harness):
    first = await harness.chat("找鸡肉")
    harness.backend.quantities[USER_ID] = {ITEM_1: 10}
    pending = await harness.chat("把第一个加入一份", first.session_id)
    response = await harness.chat("确认", pending.session_id)
    assert response.error_code == "INSUFFICIENT_STOCK_SNAPSHOT"
    assert harness.backend.write_count == 0
    assert response.pending_action is not None  # Can cancel or refresh; no dispatch occurred.


async def test_sold_out_menu_result_cannot_prepare_cart_write(harness):
    first = await harness.chat("看看菜单")
    result = await harness.agent._tool_executor.execute(
        "add_to_cart",
        '{"position":4,"quantity":1}',
        ToolContext(
            authorization="Bearer demo-token",
            current_search=SearchFilters(),
            last_search_results=(
                await harness.store.get(first.session_id)
            ).state.last_search_results,
            results_updated_at=datetime.now(UTC),
        ),
    )
    assert json.loads(result.output)["error"]["code"] == "INSUFFICIENT_STOCK_SNAPSHOT"
    assert result.pending_action is None
    assert harness.backend.write_count == 0


async def test_disappeared_item_fails_confirmation_before_write(harness):
    pending = await prepare(harness)

    async def empty_menu(*args, **kwargs):
        return []

    harness.agent._tool_executor._backend_client.get_menu = empty_menu
    result = await harness.chat("确认", pending.session_id)
    assert result.error_code == "ITEM_UNAVAILABLE"
    assert harness.backend.write_count == 0


async def test_refinement_preserves_limit_and_validates_merged_price_range(harness):
    previous = SearchFilters(min_price=10, max_price=20, limit=3)
    context = ToolContext(authorization=None, current_search=previous)
    valid = await harness.agent._tool_executor.execute(
        "search_menu", '{"keyword":"avocado"}', context
    )
    assert valid.search_state.limit == 3
    invalid = await harness.agent._tool_executor.execute("search_menu", '{"max_price":5}', context)
    assert json.loads(invalid.output)["error"]["code"] == "INVALID_TOOL_ARGUMENTS"
    assert previous.max_price == 20
