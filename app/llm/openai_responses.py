from typing import Any

from openai import AsyncOpenAI

from app.core.exceptions import AgentConfigurationError
from app.llm.base import ModelTurn, ToolCall


class OpenAIResponsesModel:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key) if api_key else None

    async def respond(
        self,
        *,
        input_items: list[Any],
        tools: list[dict[str, Any]],
        instructions: str,
    ) -> ModelTurn:
        if self._client is None:
            raise AgentConfigurationError(
                "OPENAI_API_KEY is not configured; health checks remain available."
            )

        response = await self._client.responses.create(
            model=self._model,
            instructions=instructions,
            input=input_items,
            tools=tools,
            parallel_tool_calls=False,
        )
        calls = [
            ToolCall(
                call_id=item.call_id,
                name=item.name,
                arguments=item.arguments,
            )
            for item in response.output
            if item.type == "function_call"
        ]
        return ModelTurn(
            text=response.output_text,
            tool_calls=calls,
            output_items=list(response.output),
        )
