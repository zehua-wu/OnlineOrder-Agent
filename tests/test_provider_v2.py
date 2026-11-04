import json

import httpx
import pytest
from openai import AsyncOpenAI

from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.core.config import Settings
from app.core.exceptions import AgentConfigurationError, AgentLoopError, BackendToolError
from app.llm.chat_completions import ChatCompletionsModel
from app.models.tools import SearchFilters
from app.tools.definitions import AGENT_TOOLS


@pytest.mark.parametrize(
    "provider,model_name", [("qwen", "qwen-plus"), ("deepseek", "deepseek-chat")]
)
async def test_provider_wire_contract_and_tool_result_round_trip(provider, model_name):
    requests = []

    def handle(request):
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        choice = (
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "get_cart", "arguments": "{}"},
                    }
                ],
            }
            if len(requests) == 1
            else {"role": "assistant", "content": "Cart is empty."}
        )
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 1,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls" if len(requests) == 1 else "stop",
                        "message": choice,
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )

    settings = Settings(_env_file=None, llm_provider=provider, llm_api_key="fixture-key")
    model = ChatCompletionsModel(settings)
    await model.close()
    model._client = AsyncOpenAI(
        api_key="fixture-key",
        base_url="http://provider.test/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
        max_retries=0,
    )
    try:
        inputs = [
            {"role": "developer", "content": "application state"},
            {"role": "user", "content": "show cart"},
        ]
        turn = await model.respond(input_items=inputs, tools=AGENT_TOOLS, instructions="rules")
        assert turn.tool_calls[0].name == "get_cart"
        assert turn.input_tokens == 10
        inputs.extend(turn.output_items)
        inputs.append(
            {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": '{"ok":true,"cart":{"items":[]}}',
            }
        )
        final = await model.respond(input_items=inputs, tools=AGENT_TOOLS, instructions="rules")
        assert final.text == "Cart is empty."
        path, wire = requests[-1]
        assert path == "/v1/chat/completions"
        assert wire["model"] == model_name
        assert wire["messages"][-2]["tool_calls"][0]["id"] == "call-1"
        assert wire["messages"][-1]["role"] == "tool"
        assert wire["messages"][-1]["tool_call_id"] == "call-1"
        assert wire["messages"][1]["role"] == "system"
        assert "strict" not in wire["tools"][0]["function"]
        assert "parallel_tool_calls" not in wire
        assert "fixture-key" not in json.dumps(wire)
    finally:
        await model.close()


async def test_model_missing_api_key_has_clear_configuration_error():
    model = ChatCompletionsModel(
        Settings(_env_file=None, llm_provider="qwen", llm_api_key=None, qwen_api_key=None)
    )
    with pytest.raises(AgentConfigurationError, match="LLM_API_KEY"):
        await model.respond(input_items=[], tools=[], instructions="rules")


@pytest.mark.parametrize("status", [429, 503])
async def test_backend_safe_reads_retry_bounded_transient_statuses(status):
    attempts = []

    def handle(request):
        attempts.append(request)
        return (
            httpx.Response(status, json={"message": "transient"})
            if len(attempts) == 1
            else httpx.Response(200, json=[])
        )

    async with httpx.AsyncClient(
        base_url="http://fixture.test", transport=httpx.MockTransport(handle)
    ) as http:
        result = await OnlineOrderBackendClient(http, read_retries=1).search_menu(
            SearchFilters(), authorization=None
        )
    assert result == []
    assert len(attempts) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409])
async def test_backend_does_not_retry_definite_read_failures(status):
    attempts = []

    def handle(request):
        attempts.append(request)
        return httpx.Response(status, json={"message": "Bearer secret should never be reflected"})

    async with httpx.AsyncClient(
        base_url="http://fixture.test", transport=httpx.MockTransport(handle)
    ) as http:
        with pytest.raises(BackendToolError) as error:
            await OnlineOrderBackendClient(http, read_retries=3).get_cart(
                authorization="Bearer test"
            )
    assert len(attempts) == 1
    assert "secret" not in error.value.message


@pytest.mark.parametrize("payload", [None, {"unexpected": 1}, [None], [{"menuItemId": "id"}]])
async def test_invalid_search_response_becomes_controlled_error(payload):
    async with httpx.AsyncClient(
        base_url="http://fixture.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
    ) as http:
        with pytest.raises(BackendToolError) as error:
            await OnlineOrderBackendClient(http).search_menu(SearchFilters(), authorization=None)
    assert error.value.code == "INVALID_BACKEND_RESPONSE"


async def test_invalid_json_does_not_escape_backend_boundary():
    async with httpx.AsyncClient(
        base_url="http://fixture.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="html")),
    ) as http:
        with pytest.raises(BackendToolError):
            await OnlineOrderBackendClient(http).get_cart(authorization="Bearer test")


@pytest.mark.parametrize("field", ["max_spicy_level", "limit", "vegetarian", "max_price"])
async def test_search_tool_rejects_coercion_and_nonfinite(harness, field):
    from app.tools.executor import ToolContext

    for value in [True, "2"] if field != "vegetarian" else [1, "false"]:
        result = await harness.agent._tool_executor.execute(
            "search_menu",
            json.dumps({field: value}),
            ToolContext(authorization=None, current_search=SearchFilters()),
        )
        assert json.loads(result.output)["ok"] is False
    assert harness.backend.calls == []


def test_provider_key_precedence_and_runtime_restrictions():
    qwen = Settings(
        _env_file=None, llm_api_key="generic", qwen_api_key="qwen", deepseek_api_key="deep"
    )
    assert qwen.model_api_key == "generic"
    assert "generic" not in repr(qwen)
    deep = Settings(_env_file=None, llm_provider="deepseek", deepseek_api_key="deep")
    assert deep.model_api_key == "deep"
    assert deep.model_base_url == "https://api.deepseek.com/v1"
    for overrides in (
        {"app_env": "production", "llm_provider": "mock"},
        {"app_env": "production", "session_backend": "memory"},
        {"session_ttl_seconds": 999999, "action_ttl_seconds": 3600},
    ):
        with pytest.raises(ValueError):
            Settings(_env_file=None, **overrides)


async def test_empty_and_truncated_provider_output_is_bounded():
    for choice in (
        [],
        [
            {
                "index": 0,
                "finish_reason": "length",
                "message": {"role": "assistant", "content": "partial"},
            }
        ],
    ):
        model = ChatCompletionsModel(Settings(_env_file=None, llm_api_key="fixture"))
        await model.close()
        model._client = AsyncOpenAI(
            api_key="fixture",
            base_url="http://fixture.test",
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _, choices=choice: httpx.Response(
                        200,
                        json={
                            "id": "x",
                            "object": "chat.completion",
                            "created": 1,
                            "model": "x",
                            "choices": choices,
                        },
                    )
                )
            ),
        )
        try:
            with pytest.raises(AgentLoopError):
                await model.respond(input_items=[], tools=[], instructions="rules")
        finally:
            await model.close()
