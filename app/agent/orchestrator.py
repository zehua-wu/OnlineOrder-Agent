import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.agent.prompt import SYSTEM_PROMPT
from app.core.exceptions import AgentLoopError, SessionAccessError, SessionNotFoundError
from app.llm.base import LanguageModel, ToolCall
from app.memory.base import SessionStore
from app.memory.coordinator import SessionCoordinator
from app.models.chat import ChatResponse, MenuItemCard, SearchCardsResponse
from app.models.session import ConversationMessage, ConversationSession, SearchResultReference
from app.tools.definitions import AGENT_TOOLS
from app.tools.executor import ToolContext, ToolExecutor


class AgentOrchestrator:
    _INITIAL_CARD_LIMIT = 3

    def __init__(
        self,
        *,
        model: LanguageModel,
        tool_executor: ToolExecutor,
        session_store: SessionStore,
        coordinator: SessionCoordinator,
        session_ttl_seconds: int,
        recent_message_limit: int,
        max_tool_steps: int,
    ) -> None:
        self._model = model
        self._tool_executor = tool_executor
        self._session_store = session_store
        self._coordinator = coordinator
        self._session_ttl_seconds = session_ttl_seconds
        self._recent_message_limit = recent_message_limit
        self._max_tool_steps = max_tool_steps

    async def chat(
        self,
        *,
        message: str,
        session_id: str | None,
        authorization: str | None,
    ) -> ChatResponse:
        effective_session_id = session_id or str(uuid4())
        owner = self._owner_fingerprint(authorization)

        async with self._coordinator.acquire(effective_session_id):
            session = await self._session_store.get(effective_session_id)
            if session is None:
                session = ConversationSession(
                    session_id=effective_session_id,
                    owner_fingerprint=owner,
                )
            elif session.owner_fingerprint != owner:
                raise SessionAccessError("This conversation belongs to another caller.")

            input_items = self._build_context(session, message)
            answer, tool_steps, response_results = await self._run_tool_loop(
                input_items=input_items,
                authorization=authorization,
                session=session,
            )

            session.messages.extend(
                [
                    ConversationMessage(role="user", content=message),
                    ConversationMessage(role="assistant", content=answer),
                ]
            )
            session.messages = session.messages[-self._recent_message_limit :]
            session.updated_at = datetime.now(UTC)
            await self._session_store.save(session, self._session_ttl_seconds)

        return ChatResponse(
            sessionId=effective_session_id,
            answer=answer,
            toolSteps=tool_steps,
            cards=self._to_cards(response_results[: self._INITIAL_CARD_LIMIT]),
            totalResults=len(response_results),
            hasMore=len(response_results) > self._INITIAL_CARD_LIMIT,
        )

    async def get_search_cards(
        self,
        *,
        session_id: str,
        authorization: str,
        offset: int,
        limit: int,
    ) -> SearchCardsResponse:
        owner = self._owner_fingerprint(authorization)
        async with self._coordinator.acquire(session_id):
            session = await self._session_store.get(session_id)
            if session is None:
                raise SessionNotFoundError("This conversation is no longer available.")
            if session.owner_fingerprint != owner:
                raise SessionAccessError("This conversation belongs to another caller.")
            results = session.state.last_search_results

        page = results[offset : offset + limit]
        next_offset = offset + len(page)
        return SearchCardsResponse(
            cards=self._to_cards(page),
            totalResults=len(results),
            nextOffset=next_offset,
            hasMore=next_offset < len(results),
        )

    async def _run_tool_loop(
        self,
        *,
        input_items: list[Any],
        authorization: str | None,
        session: ConversationSession,
    ) -> tuple[str, int, list[SearchResultReference]]:
        tool_steps = 0
        seen_calls: set[str] = set()
        response_results: list[SearchResultReference] = []

        while True:
            turn = await self._model.respond(
                input_items=input_items,
                tools=AGENT_TOOLS,
                instructions=SYSTEM_PROMPT,
            )
            input_items.extend(turn.output_items)

            if not turn.tool_calls:
                if not turn.text.strip():
                    raise AgentLoopError("The model returned neither text nor a tool call.")
                return turn.text.strip(), tool_steps, response_results

            for call in turn.tool_calls:
                if tool_steps >= self._max_tool_steps:
                    raise AgentLoopError("The agent exceeded its maximum tool step limit.")

                signature = self._tool_signature(call)
                if signature in seen_calls:
                    raise AgentLoopError("The agent repeated an identical tool call.")
                seen_calls.add(signature)

                result = await self._tool_executor.execute(
                    call.name,
                    call.arguments,
                    ToolContext(
                        authorization=authorization,
                        current_search=session.state.search,
                        last_search_results=session.state.last_search_results,
                    ),
                )
                if call.name == "search_menu":
                    response_results = result.search_results or []
                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": result.output,
                    }
                )
                if result.search_state is not None:
                    session.state.current_task = "MENU_SEARCH"
                    session.state.search = result.search_state
                    session.state.last_search_results = result.search_results or []
                    session.state.selected_item = None
                if result.selected_item is not None:
                    session.state.selected_item = result.selected_item
                tool_steps += 1

    @staticmethod
    def _to_cards(results: list[SearchResultReference]) -> list[MenuItemCard]:
        return [
            MenuItemCard(
                position=item.position,
                menuItemId=item.menu_item_id,
                name=item.name,
                description=item.description,
                ingredientSummary=item.ingredient_summary,
                restaurantId=item.restaurant_id,
                restaurantName=item.restaurant_name,
                price=item.price,
                imageUrl=item.image_url,
                category=item.category,
                cuisineType=item.cuisine_type,
                availableQuantity=item.available_quantity,
                primaryProtein=item.primary_protein,
                spicyLevel=item.spicy_level,
                sweetnessLevel=item.sweetness_level,
                vegetarian=item.vegetarian,
                caffeinated=item.caffeinated,
                servingTemperature=item.serving_temperature,
            )
            for item in results
        ]

    def _build_context(
        self,
        session: ConversationSession,
        message: str,
    ) -> list[dict[str, str]]:
        context: list[dict[str, str]] = []
        if session.summary:
            context.append(
                {
                    "role": "developer",
                    "content": f"Conversation summary: {session.summary}",
                }
            )
        if session.state.current_task != "NONE":
            state_for_model = session.state.model_dump(exclude_none=True)
            state_for_model["last_search_results"] = [
                {
                    "position": item.position,
                    "menu_item_id": item.menu_item_id,
                    "name": item.name,
                    "restaurant_name": item.restaurant_name,
                    "price": item.price,
                }
                for item in session.state.last_search_results
            ]
            context.append(
                {
                    "role": "developer",
                    "content": (
                        "Application-managed Working State (authoritative JSON): "
                        + json.dumps(
                            state_for_model,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    ),
                }
            )
        context.extend(
            {"role": item.role, "content": item.content}
            for item in session.messages[-self._recent_message_limit :]
        )
        context.append({"role": "user", "content": message})
        return context

    @staticmethod
    def _owner_fingerprint(authorization: str | None) -> str:
        if not authorization:
            return "anonymous"
        return hashlib.sha256(authorization.encode("utf-8")).hexdigest()

    @staticmethod
    def _tool_signature(call: ToolCall) -> str:
        try:
            normalized = json.dumps(
                json.loads(call.arguments),
                sort_keys=True,
                separators=(",", ":"),
            )
        except json.JSONDecodeError:
            normalized = call.arguments
        return f"{call.name}:{normalized}"
