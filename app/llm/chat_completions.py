"""Qwen / DeepSeek / OpenAI via their common Chat Completions contract."""

from typing import Any

from openai import AsyncOpenAI

from app.core.config import Settings
from app.core.exceptions import AgentConfigurationError, AgentLoopError
from app.llm.base import ModelTurn, ToolCall


class ChatCompletionsModel:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = (
            AsyncOpenAI(
                api_key=settings.model_api_key,
                base_url=settings.model_base_url,
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
            )
            if settings.model_api_key
            else None
        )

    @staticmethod
    def _messages(input_items: list[Any], instructions: str) -> list[dict]:
        messages: list[dict] = [{"role": "system", "content": instructions}]
        for item in input_items:
            if not isinstance(item, dict):
                raise AgentLoopError("Unsupported model history item")
            if item.get("type") == "function_call_output":
                messages.append(
                    {"role": "tool", "tool_call_id": item["call_id"], "content": item["output"]}
                )
            else:
                entry = dict(item)
                # DeepSeek/Qwen do not universally support the developer role.
                if entry.get("role") == "developer":
                    entry["role"] = "system"
                messages.append(entry)
        return messages

    async def respond(
        self, *, input_items: list[Any], tools: list[dict[str, Any]], instructions: str
    ) -> ModelTurn:
        if self._client is None:
            raise AgentConfigurationError(
                "Set LLM_API_KEY (or the selected provider's API key) in .env."
            )
        functions = [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                },
            }
            for tool in tools
        ]
        # Provider-specific strict / parallel_tool_calls parameters are deliberately
        # omitted. Validation and sequential execution are owned by the harness.
        response = await self._client.chat.completions.create(
            model=self._settings.model_name,
            messages=self._messages(input_items, instructions),
            tools=functions,
            tool_choice="auto",
            temperature=0,
            max_tokens=self._settings.llm_max_output_tokens,
        )
        if not response.choices:
            raise AgentLoopError("The provider returned no choices.")
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise AgentLoopError("The provider truncated its response.")
        message = choice.message
        calls = [
            ToolCall(call.id, call.function.name, call.function.arguments)
            for call in (message.tool_calls or [])
            if call.type == "function"
        ]
        output = {"role": "assistant", "content": message.content or ""}
        if calls:
            output["tool_calls"] = [
                {
                    "id": c.call_id,
                    "type": "function",
                    "function": {"name": c.name, "arguments": c.arguments},
                }
                for c in calls
            ]
        usage = response.usage
        return ModelTurn(
            text=message.content or "",
            tool_calls=calls,
            output_items=[output],
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )

    async def close(self) -> None:
        if self._client:
            await self._client.close()
