import asyncio
from typing import Any

import httpx

from app.core.exceptions import BackendToolError
from app.models.memory import LongTermMemory, MemoryMutation
from app.models.tools import SearchFilters


class OnlineOrderBackendClient:
    """Typed boundary around the Spring Boot application."""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        *,
        read_retries: int = 1,
    ) -> None:
        self._http_client = http_client
        self._read_retries = read_retries

    async def get_current_user(self, *, authorization: str) -> dict[str, Any]:
        response = await self._request_read(
            "GET",
            "/api/users/me",
            headers=self._authorization_headers(authorization),
        )
        body = response.json()
        if not isinstance(body, dict):
            raise BackendToolError(
                code="INVALID_BACKEND_RESPONSE",
                message="The user service returned an unexpected response.",
                status_code=response.status_code,
            )
        return body

    async def search_menu(
        self,
        args: SearchFilters,
        *,
        authorization: str | None,
    ) -> list[dict[str, Any]]:
        response = await self._request_read(
            "POST",
            "/api/search",
            json=args.to_backend_payload(),
            headers=self._authorization_headers(authorization),
        )
        body = response.json()
        if not isinstance(body, list):
            raise BackendToolError(
                code="INVALID_BACKEND_RESPONSE",
                message="The catalog service returned an unexpected response.",
                status_code=response.status_code,
            )
        return body

    async def get_user_memories(
        self,
        *,
        authorization: str,
        limit: int,
    ) -> list[LongTermMemory]:
        response = await self._request_read(
            "GET",
            "/api/agent/memories",
            params={"limit": limit},
            headers=self._authorization_headers(authorization),
        )
        return self._parse_memories(response)

    async def apply_user_memory_mutations(
        self,
        *,
        authorization: str,
        mutations: list[MemoryMutation],
    ) -> list[LongTermMemory]:
        response = await self._request_read(
            "POST",
            "/api/agent/memories/mutations",
            json={
                "mutations": [mutation.to_backend_payload() for mutation in mutations]
            },
            headers=self._authorization_headers(authorization),
        )
        return self._parse_memories(response)

    @staticmethod
    def _parse_memories(response: httpx.Response) -> list[LongTermMemory]:
        body = response.json()
        if not isinstance(body, list):
            raise BackendToolError(
                code="INVALID_BACKEND_RESPONSE",
                message="The memory service returned an unexpected response.",
                status_code=response.status_code,
            )
        try:
            return [LongTermMemory.model_validate(item) for item in body]
        except (TypeError, ValueError) as exc:
            raise BackendToolError(
                code="INVALID_BACKEND_RESPONSE",
                message="The memory service returned invalid memory data.",
                status_code=response.status_code,
            ) from exc

    async def _request_read(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self._read_retries + 1):
            try:
                response = await self._http_client.request(method, path, **kwargs)
                self._raise_for_status(response)
                return response
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt >= self._read_retries:
                    raise BackendToolError(
                        code="BACKEND_UNAVAILABLE",
                        message="The ordering service is temporarily unavailable.",
                        retryable=True,
                    ) from exc
                await asyncio.sleep(0.1 * (2**attempt))
        raise AssertionError("read retry loop ended unexpectedly")

    @staticmethod
    def _authorization_headers(authorization: str | None) -> dict[str, str]:
        return {"Authorization": authorization} if authorization else {}

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return

        codes = {
            400: ("INVALID_SEARCH_PARAMS", False),
            401: ("AUTH_REQUIRED", False),
            403: ("FORBIDDEN", False),
            404: ("NOT_FOUND", False),
            409: ("CONFLICT", False),
            429: ("RATE_LIMITED", True),
        }
        code, retryable = codes.get(
            response.status_code,
            ("BACKEND_ERROR", response.status_code >= 500),
        )
        message = OnlineOrderBackendClient._safe_error_message(response)
        raise BackendToolError(
            code=code,
            message=message,
            status_code=response.status_code,
            retryable=retryable,
        )

    @staticmethod
    def _safe_error_message(response: httpx.Response) -> str:
        fallback = "The ordering service could not complete the request."
        try:
            body = response.json()
        except ValueError:
            return fallback
        if not isinstance(body, dict):
            return fallback
        message = body.get("message")
        return message[:300] if isinstance(message, str) and message else fallback
