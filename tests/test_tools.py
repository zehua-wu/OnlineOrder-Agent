import json

import pytest

from app.models.session import SearchResultReference
from app.models.tools import SearchFilters, SearchMenuArgs
from app.tools.executor import ToolContext, ToolExecutor


class FakeBackend:
    def __init__(self) -> None:
        self.searches = []

    async def search_menu(self, args, *, authorization):
        self.searches.append(args)
        assert authorization is None
        return [
            {
                "menuItemId": "item-1",
                "menuItemName": "Chicken Bowl",
                "restaurantName": "Bowl House",
                "price": 12.99,
                "imageUrl": "https://example.com/chicken.jpg",
                "availableQuantity": 8,
                "spicyLevel": 1,
                "servingTemperature": "HOT",
            }
        ]


def test_search_args_reject_inverted_price_range() -> None:
    with pytest.raises(ValueError, match="min_price"):
        SearchMenuArgs(min_price=20, max_price=10)


@pytest.mark.asyncio
async def test_executor_returns_structured_tool_output() -> None:
    backend = FakeBackend()
    executor = ToolExecutor(backend)
    result = await executor.execute(
        "search_menu",
        '{"primary_protein":"CHICKEN"}',
        ToolContext(authorization=None, current_search=SearchFilters()),
    )
    assert json.loads(result.output) == {
        "ok": True,
        "effectiveFilters": {"primary_protein": "CHICKEN", "limit": 10},
        "count": 1,
        "items": [
            {
                "menuItemId": "item-1",
                "menuItemName": "Chicken Bowl",
                "restaurantName": "Bowl House",
                "price": 12.99,
                "imageUrl": "https://example.com/chicken.jpg",
                "availableQuantity": 8,
                "spicyLevel": 1,
                "servingTemperature": "HOT",
            }
        ],
    }
    assert result.search_state == SearchFilters(primary_protein="CHICKEN")
    assert result.search_results is not None
    assert result.search_results[0].menu_item_id == "item-1"
    assert result.search_results[0].image_url == "https://example.com/chicken.jpg"
    assert result.search_results[0].available_quantity == 8
    assert result.search_results[0].spicy_level == 1


@pytest.mark.asyncio
async def test_refinement_inherits_previous_search_filters() -> None:
    backend = FakeBackend()
    executor = ToolExecutor(backend)
    previous = SearchFilters(
        primary_protein="CHICKEN",
        max_spicy_level=1,
        max_price=15,
    )

    result = await executor.execute(
        "search_menu",
        '{"keyword":"avocado","start_new_search":false}',
        ToolContext(authorization=None, current_search=previous),
    )

    assert result.search_state == SearchFilters(
        keyword="avocado",
        primary_protein="CHICKEN",
        max_spicy_level=1,
        max_price=15,
    )
    assert backend.searches[-1].to_backend_payload() == {
        "keyword": "avocado",
        "primaryProtein": "CHICKEN",
        "maxSpicyLevel": 1,
        "maxPrice": 15.0,
        "limit": 10,
    }


@pytest.mark.asyncio
async def test_keyword_drops_protein_already_expressed_structurally() -> None:
    backend = FakeBackend()
    executor = ToolExecutor(backend)

    result = await executor.execute(
        "search_menu",
        '{"keyword":"avocado chicken","primary_protein":"CHICKEN"}',
        ToolContext(authorization=None, current_search=SearchFilters()),
    )

    assert result.search_state is not None
    assert result.search_state.keyword == "avocado"
    assert result.search_state.primary_protein == "CHICKEN"
    assert backend.searches[-1].to_backend_payload()["keyword"] == "avocado"


@pytest.mark.asyncio
async def test_new_search_resets_previous_filters_and_can_clear_one() -> None:
    backend = FakeBackend()
    executor = ToolExecutor(backend)
    previous = SearchFilters(primary_protein="CHICKEN", max_price=15)

    new_search = await executor.execute(
        "search_menu",
        '{"cuisine_type":"JAPANESE","start_new_search":true}',
        ToolContext(authorization=None, current_search=previous),
    )
    assert new_search.search_state == SearchFilters(cuisine_type="JAPANESE")

    cleared = await executor.execute(
        "search_menu",
        '{"clear_filters":["max_price"]}',
        ToolContext(authorization=None, current_search=previous),
    )
    assert cleared.search_state == SearchFilters(primary_protein="CHICKEN")


@pytest.mark.asyncio
async def test_select_search_result_resolves_position_without_changing_cart() -> None:
    backend = FakeBackend()
    executor = ToolExecutor(backend)
    results = [
        SearchResultReference(position=1, menu_item_id="item-1", name="First"),
        SearchResultReference(
            position=2,
            menu_item_id="item-2",
            name="Avocado Chicken Sushi Wrap",
            restaurant_name="Harbor Bento Lab",
            price=11.75,
        ),
    ]

    result = await executor.execute(
        "select_search_result",
        '{"position":2}',
        ToolContext(
            authorization=None,
            current_search=SearchFilters(),
            last_search_results=results,
        ),
    )

    assert result.selected_item is not None
    assert result.selected_item.menu_item_id == "item-2"
    assert json.loads(result.output)["cartChanged"] is False
    assert backend.searches == []


@pytest.mark.asyncio
async def test_select_search_result_rejects_missing_position() -> None:
    executor = ToolExecutor(FakeBackend())
    result = await executor.execute(
        "select_search_result",
        '{"position":3}',
        ToolContext(
            authorization=None,
            current_search=SearchFilters(),
            last_search_results=[],
        ),
    )

    assert result.selected_item is None
    assert json.loads(result.output)["error"]["code"] == "SEARCH_RESULT_NOT_FOUND"
