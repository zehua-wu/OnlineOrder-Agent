import json
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.core.exceptions import BackendToolError
from app.models.session import SearchResultReference, SelectedItem
from app.models.tools import SearchFilters, SearchMenuArgs, SelectSearchResultArgs


@dataclass(frozen=True)
class ToolContext:
    authorization: str | None
    current_search: SearchFilters
    last_search_results: list[SearchResultReference] = field(default_factory=list)


@dataclass(frozen=True)
class ToolExecutionResult:
    output: str
    search_state: SearchFilters | None = None
    search_results: list[SearchResultReference] | None = None
    selected_item: SelectedItem | None = None


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
        if name == "select_search_result":
            return self._select_search_result(arguments, context)
        if name != "search_menu":
            return ToolExecutionResult(
                output=self._error("UNKNOWN_TOOL", f"Tool '{name}' is not available.")
            )

        try:
            raw_args = json.loads(arguments)
            parsed_args = SearchMenuArgs.model_validate(raw_args)
            effective_filters = self._merge_search_filters(
                current=context.current_search,
                update=parsed_args,
            )
            effective_filters = self._remove_redundant_protein_keyword(
                effective_filters
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            return ToolExecutionResult(
                output=self._error("INVALID_TOOL_ARGUMENTS", str(exc))
            )

        try:
            items = await self._backend_client.search_menu(
                effective_filters,
                authorization=context.authorization,
            )
        except BackendToolError as exc:
            return ToolExecutionResult(
                output=json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "retryable": exc.retryable,
                        },
                    },
                    ensure_ascii=False,
                )
            )

        references = self._result_references(items)
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
            search_results=references,
        )

    def _select_search_result(
        self,
        arguments: str,
        context: ToolContext,
    ) -> ToolExecutionResult:
        try:
            raw_args = json.loads(arguments)
            parsed_args = SelectSearchResultArgs.model_validate(raw_args)
        except (json.JSONDecodeError, ValidationError) as exc:
            return ToolExecutionResult(
                output=self._error("INVALID_TOOL_ARGUMENTS", str(exc))
            )

        result = next(
            (
                item
                for item in context.last_search_results
                if item.position == parsed_args.position
            ),
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

        for field in update.clear_filters:
            merged[field] = None
        for field in SearchFilters.FILTER_FIELDS:
            value = getattr(update, field)
            if value is not None:
                merged[field] = value

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
                    ingredient_summary=ToolExecutor._optional_string(
                        item.get("ingredientSummary")
                    ),
                    restaurant_name=(
                        restaurant_name if isinstance(restaurant_name, str) else None
                    ),
                    restaurant_id=ToolExecutor._optional_string(item.get("restaurantId")),
                    price=price,
                    image_url=ToolExecutor._optional_string(item.get("imageUrl")),
                    category=ToolExecutor._optional_string(item.get("category")),
                    cuisine_type=ToolExecutor._optional_string(item.get("cuisineType")),
                    available_quantity=ToolExecutor._optional_int(
                        item.get("availableQuantity")
                    ),
                    primary_protein=ToolExecutor._optional_string(
                        item.get("primaryProtein")
                    ),
                    spicy_level=ToolExecutor._optional_int(item.get("spicyLevel")),
                    sweetness_level=ToolExecutor._optional_int(
                        item.get("sweetnessLevel")
                    ),
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
