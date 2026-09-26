import json

import httpx
import pytest

from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.core.exceptions import BackendToolError
from app.models.memory import MemoryMutation
from app.models.tools import SearchMenuArgs


@pytest.mark.asyncio
async def test_search_menu_maps_fields_and_forwards_authorization() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=[{"menuItemId": "item-1", "menuItemName": "Chicken Bowl"}],
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://backend.test",
    ) as http_client:
        client = OnlineOrderBackendClient(http_client)
        result = await client.search_menu(
            SearchMenuArgs(
                keyword="avocado",
                primary_protein="CHICKEN",
                max_spicy_level=1,
                max_price=15,
            ),
            authorization="Bearer customer-token",
        )

    assert result[0]["menuItemName"] == "Chicken Bowl"
    assert captured == {
        "path": "/api/search",
        "authorization": "Bearer customer-token",
        "body": {
            "keyword": "avocado",
            "primaryProtein": "CHICKEN",
            "maxSpicyLevel": 1,
            "maxPrice": 15.0,
            "limit": 10,
        },
    }


@pytest.mark.asyncio
async def test_search_menu_translates_backend_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "Too many requests"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://backend.test",
    ) as http_client:
        client = OnlineOrderBackendClient(http_client, read_retries=0)
        with pytest.raises(BackendToolError) as raised:
            await client.search_menu(SearchMenuArgs(), authorization=None)

    assert raised.value.code == "RATE_LIMITED"
    assert raised.value.retryable is True


@pytest.mark.asyncio
async def test_user_memory_calls_are_scoped_by_forwarded_authorization() -> None:
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(
            {
                "method": request.method,
                "path": request.url.path,
                "query": request.url.query.decode(),
                "authorization": request.headers.get("Authorization"),
                "body": json.loads(request.content) if request.content else None,
            }
        )
        return httpx.Response(
            200,
            json=[{"key": "spice.preference", "value": "Prefers mild food"}],
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://backend.test",
    ) as http_client:
        client = OnlineOrderBackendClient(http_client)
        memories = await client.get_user_memories(
            authorization="Bearer customer-token",
            limit=50,
        )
        await client.apply_user_memory_mutations(
            authorization="Bearer customer-token",
            mutations=[
                MemoryMutation(
                    operation="UPSERT",
                    key="spice.preference",
                    value="Prefers mild food",
                )
            ],
        )

    assert memories[0].key == "spice.preference"
    assert captured == [
        {
            "method": "GET",
            "path": "/api/agent/memories",
            "query": "limit=50",
            "authorization": "Bearer customer-token",
            "body": None,
        },
        {
            "method": "POST",
            "path": "/api/agent/memories/mutations",
            "query": "",
            "authorization": "Bearer customer-token",
            "body": {
                "mutations": [
                    {
                        "operation": "UPSERT",
                        "key": "spice.preference",
                        "value": "Prefers mild food",
                    }
                ]
            },
        },
    ]
