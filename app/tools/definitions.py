from typing import Any

from app.models.tools import AddToCartArgs, EmptyArgs, GetMenuArgs


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


SEARCH_MENU_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "search_menu",
    "description": (
        "Search the live Spring Boot catalog. Call this immediately for any concrete "
        "food/drink search or recommendation, even when the user supplies only one "
        "filter; unspecified filters are optional and are not a reason to ask a "
        "follow-up question. In a follow-up refinement, provide only new or changed "
        "filter values and set start_new_search=false: FastAPI will merge them with "
        "the stored search state. Set start_new_search=true only when the user "
        "explicitly abandons the prior search and starts a different one. Do not put "
        "protein words such as chicken into keyword when primary_protein already "
        "expresses that constraint."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": _nullable({"type": "string", "maxLength": 100}),
            "cuisine_type": _nullable(
                {
                    "type": "string",
                    "enum": [
                        "AMERICAN",
                        "CHINESE",
                        "MEXICAN",
                        "ITALIAN",
                        "JAPANESE",
                        "KOREAN",
                        "INDIAN",
                        "THAI",
                        "MEDITERRANEAN",
                        "OTHER",
                    ],
                }
            ),
            "category": _nullable({"type": "string", "maxLength": 50}),
            "primary_protein": _nullable(
                {
                    "type": "string",
                    "enum": [
                        "CHICKEN",
                        "BEEF",
                        "PORK",
                        "LAMB",
                        "FISH",
                        "SHRIMP",
                        "TOFU",
                        "EGG",
                        "NONE",
                        "OTHER",
                    ],
                }
            ),
            "max_spicy_level": _nullable({"type": "integer", "minimum": 0, "maximum": 4}),
            "max_sweetness_level": _nullable({"type": "integer", "minimum": 0, "maximum": 4}),
            "vegetarian": _nullable({"type": "boolean"}),
            "caffeinated": _nullable({"type": "boolean"}),
            "serving_temperature": _nullable(
                {
                    "type": "string",
                    "enum": ["HOT", "COLD", "ROOM"],
                }
            ),
            "min_price": _nullable({"type": "number", "minimum": 0}),
            "max_price": _nullable({"type": "number", "minimum": 0}),
            "limit": _nullable({"type": "integer", "minimum": 1, "maximum": 100}),
            "start_new_search": {
                "type": "boolean",
                "description": (
                    "False for the first search and normal refinements. True only "
                    "when the user explicitly starts over with a different search."
                ),
            },
            "clear_filters": {
                "type": "array",
                "description": (
                    "Stored filters the user explicitly asked to remove. Usually empty."
                ),
                "items": {
                    "type": "string",
                    "enum": [
                        "keyword",
                        "cuisine_type",
                        "category",
                        "primary_protein",
                        "max_spicy_level",
                        "max_sweetness_level",
                        "vegetarian",
                        "caffeinated",
                        "serving_temperature",
                        "min_price",
                        "max_price",
                    ],
                },
            },
        },
        "required": [
            "keyword",
            "cuisine_type",
            "category",
            "primary_protein",
            "max_spicy_level",
            "max_sweetness_level",
            "vegetarian",
            "caffeinated",
            "serving_temperature",
            "min_price",
            "max_price",
            "limit",
            "start_new_search",
            "clear_filters",
        ],
        "additionalProperties": False,
    },
}


SELECT_SEARCH_RESULT_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "select_search_result",
    "description": (
        "Select one item from the application-managed last_search_results by its "
        "displayed position. Use this when the user expresses a choice or preference, "
        "such as 'the second one looks good' or 'choose number 3'. This only records "
        "selected_item in conversation state; it does not add anything to a cart. "
        "Do not call it when the user merely asks what an item was."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "position": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "One-based position from last_search_results.",
            }
        },
        "required": ["position"],
        "additionalProperties": False,
    },
}


def _tool(name, description, args):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": args.model_json_schema(),
    }


LIST_RESTAURANTS_TOOL = _tool(
    "list_restaurants",
    "List open restaurants. Use returned IDs for get_menu; never guess restaurant IDs.",
    EmptyArgs,
)
GET_MENU_TOOL = _tool(
    "get_menu",
    "View a known restaurant's menu, including sellable and inventory snapshot fields. restaurant_id must come from saved restaurants/search results.",
    GetMenuArgs,
)
GET_CART_TOOL = _tool(
    "get_cart",
    "Read the authenticated customer's live cart. No user ID argument exists.",
    EmptyArgs,
)
ADD_TO_CART_TOOL = _tool(
    "add_to_cart",
    "Prepare (never execute) adding quantity units of a known result position or selected_item to the cart. The app asks for confirmation in a later user turn. Use only for an explicit add request, never merely liking/selecting an item. No guessed menu ID, price, user ID, or confirmation argument is accepted.",
    AddToCartArgs,
)
AGENT_TOOLS = [
    SEARCH_MENU_TOOL,
    SELECT_SEARCH_RESULT_TOOL,
    LIST_RESTAURANTS_TOOL,
    GET_MENU_TOOL,
    GET_CART_TOOL,
    ADD_TO_CART_TOOL,
]
