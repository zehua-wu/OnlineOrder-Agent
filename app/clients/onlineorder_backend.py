import asyncio
import random
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.exceptions import BackendToolError
from app.models.memory import LongTermMemory, MemoryMutation
from app.models.tools import SearchFilters


class CartItem(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    id: str
    menu_item_id: str = Field(alias="menuItemId")
    name: str
    price: float = Field(ge=0, allow_inf_nan=False)
    image_url: str | None = Field(default=None, alias="imageUrl")
    quantity: int = Field(ge=1, strict=True)
    subtotal: float = Field(ge=0, allow_inf_nan=False)


class CartSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    id: str | None
    user_id: str = Field(alias="userId")
    status: str
    items: list[CartItem]
    total_amount: float = Field(alias="totalAmount", ge=0, allow_inf_nan=False)


class OnlineOrderBackendClient:
    """Only endpoints verified in OnlineOrder-Dev (see docs/api-contract-zh.md)."""

    def __init__(self, http_client: httpx.AsyncClient, *, read_retries: int = 1) -> None:
        self._http_client = http_client
        self._read_retries = read_retries

    async def get_current_user(self, *, authorization: str) -> dict[str, Any]:
        response = await self._request_read(
            "GET", "/api/users/me", headers=self._authorization_headers(authorization)
        )
        return self._body(response, dict)

    async def search_menu(self, args: SearchFilters, *, authorization: str | None) -> list[dict]:
        response = await self._request_read(
            "POST",
            "/api/search",
            json=args.to_backend_payload(),
            headers=self._authorization_headers(authorization),
        )
        items = self._body(response, list)
        if any(
            not isinstance(i.get("menuItemId"), str) or not isinstance(i.get("menuItemName"), str)
            for i in items
        ):
            raise self._invalid_response()
        return items

    async def list_restaurants(self, *, authorization: str | None) -> list[dict]:
        response = await self._request_read(
            "GET", "/api/restaurants", headers=self._authorization_headers(authorization)
        )
        items = self._body(response, list)
        if any(
            not isinstance(i.get("id"), str) or not isinstance(i.get("name"), str) for i in items
        ):
            raise self._invalid_response()
        return items

    async def get_menu(self, restaurant_id: str, *, authorization: str | None) -> list[dict]:
        response = await self._request_read(
            "GET",
            f"/api/restaurants/{restaurant_id}/menu",
            headers=self._authorization_headers(authorization),
        )
        items = self._body(response, list)
        if any(
            not isinstance(i.get("id"), str) or not isinstance(i.get("name"), str) for i in items
        ):
            raise self._invalid_response()
        return items

    async def get_cart(self, *, authorization: str) -> dict:
        response = await self._request_read(
            "GET", "/api/cart", headers=self._authorization_headers(authorization)
        )
        return self._cart(response)

    async def add_to_cart(self, menu_item_id: str, quantity: int, *, authorization: str) -> dict:
        # This backend INCREMENTS quantity and has no idempotency-key contract.
        # Send once. Timeout / 5xx / malformed success means UNKNOWN, never retry.
        try:
            response = await self._http_client.post(
                "/api/cart/items",
                json={"menuItemId": menu_item_id, "quantity": quantity},
                headers=self._authorization_headers(authorization),
            )
        except httpx.RequestError as error:
            raise BackendToolError(
                code="WRITE_OUTCOME_UNKNOWN",
                message="The cart update may have been applied; inspect the cart before another write.",
                outcome_unknown=True,
            ) from error
        if response.status_code >= 500:
            raise BackendToolError(
                code="WRITE_OUTCOME_UNKNOWN",
                message="The cart update result is unknown; inspect the cart.",
                status_code=response.status_code,
                outcome_unknown=True,
            )
        self._raise_for_status(response)
        try:
            return self._cart(response)
        except BackendToolError as error:
            raise BackendToolError(
                code="WRITE_OUTCOME_UNKNOWN",
                message="The cart changed but its response could not be validated; inspect the cart.",
                outcome_unknown=True,
            ) from error

    async def get_user_memories(self, *, authorization: str, limit: int) -> list[LongTermMemory]:
        response = await self._request_read(
            "GET",
            "/api/agent/memories",
            params={"limit": limit},
            headers=self._authorization_headers(authorization),
        )
        return self._parse_memories(response)

    async def apply_user_memory_mutations(
        self, *, authorization: str, mutations: list[MemoryMutation]
    ) -> list[LongTermMemory]:
        # Verified UPSERT / DELETE are idempotent assignments, unlike cart increments.
        response = await self._request_read(
            "POST",
            "/api/agent/memories/mutations",
            json={"mutations": [m.to_backend_payload() for m in mutations]},
            headers=self._authorization_headers(authorization),
        )
        return self._parse_memories(response)

    @classmethod
    def _cart(cls, response: httpx.Response) -> dict:
        try:
            return CartSnapshot.model_validate(cls._body(response, dict)).model_dump(by_alias=True)
        except ValidationError as error:
            raise cls._invalid_response() from error

    @classmethod
    def _parse_memories(cls, response: httpx.Response) -> list[LongTermMemory]:
        try:
            return [LongTermMemory.model_validate(i) for i in cls._body(response, list)]
        except (TypeError, ValueError) as error:
            raise cls._invalid_response() from error

    @staticmethod
    def _invalid_response() -> BackendToolError:
        return BackendToolError(
            code="INVALID_BACKEND_RESPONSE", message="The ordering service returned invalid data."
        )

    @classmethod
    def _body(cls, response: httpx.Response, expected: type) -> Any:
        try:
            body = response.json()
        except ValueError as error:
            raise cls._invalid_response() from error
        if not isinstance(body, expected) or (
            expected is list and any(not isinstance(i, dict) for i in body)
        ):
            raise cls._invalid_response()
        return body

    async def _request_read(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self._read_retries + 1):
            try:
                response = await self._http_client.request(method, path, **kwargs)
                self._raise_for_status(response)
                return response
            except httpx.RequestError as error:
                failure = BackendToolError(
                    code="BACKEND_UNAVAILABLE",
                    message="The ordering service is temporarily unavailable.",
                    retryable=True,
                )
                failure.__cause__ = error
            except BackendToolError as error:
                failure = error
            if not failure.retryable or attempt == self._read_retries:
                raise failure
            # Deliberately bounded; do not honor an arbitrarily large Retry-After.
            await asyncio.sleep(min(0.1 * 2**attempt + random.uniform(0, 0.05), 0.8))
        raise AssertionError("retry loop ended unexpectedly")

    @staticmethod
    def _authorization_headers(authorization: str | None) -> dict[str, str]:
        return {"Authorization": authorization} if authorization else {}

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        codes = {
            400: ("INVALID_BACKEND_PARAMS", False),
            401: ("AUTH_REQUIRED", False),
            403: ("FORBIDDEN", False),
            404: ("NOT_FOUND", False),
            409: ("CONFLICT", False),
            429: ("RATE_LIMITED", True),
        }
        code, retryable = codes.get(
            response.status_code, ("BACKEND_ERROR", response.status_code >= 500)
        )
        # Never reflect raw backend bodies (which may contain secrets or instructions).
        raise BackendToolError(
            code=code,
            message=f"The ordering service rejected the request ({code}).",
            status_code=response.status_code,
            retryable=retryable,
        )
