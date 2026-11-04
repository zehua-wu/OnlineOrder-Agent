import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.core.exceptions import BackendToolError
from app.models.harness import PendingAction
from app.models.session import SearchResultReference, SelectedItem
from app.models.tools import (
    AddToCartArgs,
    EmptyArgs,
    GetMenuArgs,
    SearchFilters,
    SearchMenuArgs,
    SelectSearchResultArgs,
)


@dataclass(frozen=True)
class ToolContext:
    authorization: str | None
    current_search: SearchFilters
    last_search_results: list[SearchResultReference] = field(default_factory=list)
    selected_item: SelectedItem | None = None
    last_restaurants: list[dict] = field(default_factory=list)
    results_updated_at: datetime | None = None
    pending_ttl_seconds: int = 300
    reference_ttl_seconds: int = 900


@dataclass(frozen=True)
class ToolExecutionResult:
    output: str
    search_state: SearchFilters | None = None
    search_results: list[SearchResultReference] | None = None
    selected_item: SelectedItem | None = None
    pending_action: PendingAction | None = None
    cart: dict | None = None
    restaurants: list[dict] | None = None


class ToolExecutor:
    _PROTEIN_KEYWORD_TERMS = {
        "CHICKEN": ("chicken", "鸡肉"),
        "BEEF": ("beef", "牛肉"),
        "PORK": ("pork", "猪肉"),
        "LAMB": ("lamb", "羊肉"),
        "FISH": ("fish", "鱼肉"),
        "SHRIMP": ("shrimp", "prawn", "虾肉"),
        "TOFU": ("tofu", "豆腐"),
        "EGG": ("egg", "鸡蛋"),
    }

    def __init__(self, backend_client: OnlineOrderBackendClient) -> None:
        self._backend_client = backend_client

    async def execute(
        self,
        name: str,
        arguments: str,
        context: ToolContext,
    ) -> ToolExecutionResult:
        parsers = {
            "search_menu": SearchMenuArgs,
            "select_search_result": SelectSearchResultArgs,
            "list_restaurants": EmptyArgs,
            "get_menu": GetMenuArgs,
            "get_cart": EmptyArgs,
            "add_to_cart": AddToCartArgs,
        }
        if name not in parsers:
            return ToolExecutionResult(
                output=self._error("UNKNOWN_TOOL", "This tool is not available.")
            )
        try:
            if len(arguments) > 16000:
                raise ValueError("arguments too long")
            parsed = parsers[name].model_validate_json(arguments)
            if name == "select_search_result":
                return self._select_search_result(arguments, context)
            if name == "add_to_cart":
                return self._prepare_add(parsed, context)
            if name == "get_cart":
                if not context.authorization:
                    return ToolExecutionResult(
                        output=self._error("AUTH_REQUIRED", "Customer login is required.")
                    )
                cart = await self._backend_client.get_cart(authorization=context.authorization)
                return ToolExecutionResult(output=json.dumps({"ok": True, "cart": cart}), cart=cart)
            if name == "list_restaurants":
                items = await self._backend_client.list_restaurants(
                    authorization=context.authorization
                )
                # Only expose useful public restaurant data, never merchant/user IDs.
                items = [
                    {k: i[k] for k in ("id", "name", "description", "status") if k in i}
                    for i in items
                ]
                return ToolExecutionResult(
                    output=json.dumps(
                        {"ok": True, "restaurants": items[:100], "truncated": len(items) > 100},
                        ensure_ascii=False,
                    ),
                    restaurants=items[:100],
                )
            if name == "get_menu":
                restaurant_id = str(UUID(parsed.restaurant_id))
                known = {str(i.get("id")) for i in context.last_restaurants}
                known.update(
                    i.restaurant_id for i in context.last_search_results if i.restaurant_id
                )
                if restaurant_id not in known:
                    return ToolExecutionResult(
                        output=self._error(
                            "UNKNOWN_RESTAURANT",
                            "List restaurants or search before choosing a restaurant.",
                        )
                    )
                items = await self._backend_client.get_menu(
                    restaurant_id, authorization=context.authorization
                )
                converted = [
                    {**i, "menuItemId": i["id"], "menuItemName": i["name"]} for i in items[:100]
                ]
                return ToolExecutionResult(
                    output=json.dumps(
                        {"ok": True, "items": items[:100], "truncated": len(items) > 100},
                        ensure_ascii=False,
                    ),
                    search_results=self._result_references(converted),
                )
            effective_filters = self._remove_redundant_protein_keyword(
                self._merge_search_filters(current=context.current_search, update=parsed)
            )
            items = await self._backend_client.search_menu(
                effective_filters, authorization=context.authorization
            )
            return ToolExecutionResult(
                output=json.dumps(
                    {
                        "ok": True,
                        "effectiveFilters": effective_filters.model_dump(exclude_none=True),
                        "count": len(items),
                        "items": items,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
                search_state=effective_filters,
                search_results=self._result_references(items),
            )
        except (ValueError, ValidationError):
            # Never echo Pydantic's raw input (it could contain a JWT or injection).
            return ToolExecutionResult(
                output=self._error(
                    "INVALID_TOOL_ARGUMENTS",
                    "Arguments must match the tool JSON schema and valid merged filter ranges.",
                )
            )
        except BackendToolError as error:
            return ToolExecutionResult(
                output=json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": error.code,
                            "message": error.message,
                            "retryable": error.retryable,
                        },
                    },
                    ensure_ascii=False,
                )
            )

    def _prepare_add(self, args: AddToCartArgs, context: ToolContext) -> ToolExecutionResult:
        if not context.authorization:
            return ToolExecutionResult(
                output=self._error("AUTH_REQUIRED", "Customer login is required.")
            )
        if (
            not context.results_updated_at
            or (datetime.now(UTC) - context.results_updated_at).total_seconds()
            > context.reference_ttl_seconds
        ):
            return ToolExecutionResult(
                output=self._error("STALE_RESULT", "Search or browse the menu again before adding.")
            )
        item = next(
            (
                i
                for i in context.last_search_results
                if (
                    i.position == args.position
                    if args.position is not None
                    else context.selected_item is not None
                    and i.menu_item_id == context.selected_item.menu_item_id
                )
            ),
            None,
        )
        if item is None:
            return ToolExecutionResult(
                output=self._error(
                    "ITEM_REFERENCE_REQUIRED",
                    "Specify a displayed position or select a result first.",
                )
            )
        # Validate the referenced real backend ID as well as the model arguments.
        UUID(item.menu_item_id)
        if item.available_quantity is not None and args.quantity > item.available_quantity:
            return ToolExecutionResult(
                output=self._error(
                    "INSUFFICIENT_STOCK_SNAPSHOT",
                    "Requested quantity exceeds the last inventory snapshot.",
                )
            )
        action = PendingAction(
            action_id=str(uuid4()),
            menu_item_id=item.menu_item_id,
            restaurant_id=item.restaurant_id,
            name=item.name,
            quantity=args.quantity,
            expires_at=datetime.now(UTC) + timedelta(seconds=context.pending_ttl_seconds),
        )
        return ToolExecutionResult(
            output=json.dumps(
                {
                    "ok": True,
                    "requiresConfirmation": True,
                    "pendingAction": action.model_dump(mode="json"),
                    "cartChanged": False,
                },
                ensure_ascii=False,
            ),
            pending_action=action,
        )

    async def check_add(self, action: PendingAction, *, authorization: str) -> None:
        cart = await self._backend_client.get_cart(authorization=authorization)
        if action.restaurant_id:
            items = await self._backend_client.get_menu(
                action.restaurant_id, authorization=authorization
            )
            item = next((i for i in items if i.get("id") == action.menu_item_id), None)
            if not item or item.get("sellable") is False or item.get("available") is False:
                raise BackendToolError(
                    code="ITEM_UNAVAILABLE", message="The item is no longer available."
                )
            in_cart = sum(
                i["quantity"] for i in cart["items"] if i["menuItemId"] == action.menu_item_id
            )
            stock = item.get("availableQuantity")
            if isinstance(stock, int) and in_cart + action.quantity > stock:
                raise BackendToolError(
                    code="INSUFFICIENT_STOCK_SNAPSHOT",
                    message="The combined quantity exceeds the current inventory snapshot.",
                )

    async def commit_add(self, action: PendingAction, *, authorization: str) -> dict:
        return await self._backend_client.add_to_cart(
            action.menu_item_id, action.quantity, authorization=authorization
        )

    async def read_cart(self, *, authorization: str) -> dict:
        return await self._backend_client.get_cart(authorization=authorization)

    def _select_search_result(
        self,
        arguments: str,
        context: ToolContext,
    ) -> ToolExecutionResult:
        try:
            raw_args = json.loads(arguments)
            parsed_args = SelectSearchResultArgs.model_validate(raw_args)
        except (json.JSONDecodeError, ValidationError):
            return ToolExecutionResult(
                output=self._error("INVALID_TOOL_ARGUMENTS", "Invalid result position.")
            )

        result = next(
            (item for item in context.last_search_results if item.position == parsed_args.position),
            None,
        )
        if result is None:
            return ToolExecutionResult(
                output=self._error(
                    "SEARCH_RESULT_NOT_FOUND",
                    f"There is no result at position {parsed_args.position}.",
                )
            )

        selected = SelectedItem(
            menu_item_id=result.menu_item_id,
            name=result.name,
            restaurant_name=result.restaurant_name,
            price=result.price,
        )
        return ToolExecutionResult(
            output=json.dumps(
                {
                    "ok": True,
                    "selectedItem": selected.model_dump(exclude_none=True),
                    "cartChanged": False,
                },
                ensure_ascii=False,
            ),
            selected_item=selected,
        )

    @staticmethod
    def _merge_search_filters(
        *,
        current: SearchFilters,
        update: SearchMenuArgs,
    ) -> SearchFilters:
        base = SearchFilters() if update.start_new_search else current.model_copy(deep=True)
        merged = base.model_dump()

        for filter_name in update.clear_filters:
            merged[filter_name] = None
        for filter_name in SearchFilters.FILTER_FIELDS:
            value = getattr(update, filter_name)
            if value is not None and filter_name in update.model_fields_set:
                merged[filter_name] = value

        return SearchFilters.model_validate(merged)

    @classmethod
    def _remove_redundant_protein_keyword(
        cls,
        filters: SearchFilters,
    ) -> SearchFilters:
        keyword = filters.keyword
        protein = filters.primary_protein
        if not keyword or not protein:
            return filters

        normalized = keyword
        for term in cls._PROTEIN_KEYWORD_TERMS.get(protein, ()):
            if term.isascii():
                normalized = re.sub(
                    rf"(?<!\w){re.escape(term)}(?!\w)",
                    " ",
                    normalized,
                    flags=re.IGNORECASE,
                )
            else:
                normalized = normalized.replace(term, " ")
        normalized = re.sub(r"\s+", " ", normalized).strip(" ,;/+-_")
        return filters.model_copy(update={"keyword": normalized or None})

    @staticmethod
    def _result_references(items: list[dict[str, object]]) -> list[SearchResultReference]:
        references: list[SearchResultReference] = []
        for position, item in enumerate(items, start=1):
            menu_item_id = item.get("menuItemId")
            name = item.get("menuItemName")
            if menu_item_id is None or not isinstance(name, str):
                continue
            raw_price = item.get("price")
            try:
                price = float(raw_price) if raw_price is not None else None
            except (TypeError, ValueError):
                price = None
            restaurant_name = item.get("restaurantName")
            references.append(
                SearchResultReference(
                    position=position,
                    menu_item_id=str(menu_item_id),
                    name=name,
                    description=ToolExecutor._optional_string(item.get("description")),
                    ingredient_summary=ToolExecutor._optional_string(item.get("ingredientSummary")),
                    restaurant_name=(restaurant_name if isinstance(restaurant_name, str) else None),
                    restaurant_id=ToolExecutor._optional_string(item.get("restaurantId")),
                    price=price,
                    image_url=ToolExecutor._optional_string(item.get("imageUrl")),
                    category=ToolExecutor._optional_string(item.get("category")),
                    cuisine_type=ToolExecutor._optional_string(item.get("cuisineType")),
                    available_quantity=ToolExecutor._optional_int(item.get("availableQuantity")),
                    primary_protein=ToolExecutor._optional_string(item.get("primaryProtein")),
                    spicy_level=ToolExecutor._optional_int(item.get("spicyLevel")),
                    sweetness_level=ToolExecutor._optional_int(item.get("sweetnessLevel")),
                    vegetarian=ToolExecutor._optional_bool(item.get("vegetarian")),
                    caffeinated=ToolExecutor._optional_bool(item.get("caffeinated")),
                    serving_temperature=ToolExecutor._optional_string(
                        item.get("servingTemperature")
                    ),
                )
            )
        return references

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value is None:
            return None
        return value if isinstance(value, str) else str(value)

    @staticmethod
    def _optional_int(value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_bool(value: object) -> bool | None:
        return value if isinstance(value, bool) else None

    @staticmethod
    def _error(code: str, message: str) -> str:
        return json.dumps(
            {"ok": False, "error": {"code": code, "message": message, "retryable": False}},
            ensure_ascii=False,
        )
