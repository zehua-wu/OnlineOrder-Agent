from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import openai
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.agent.orchestrator import AgentOrchestrator
from app.api.routes import router
from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AgentConfigurationError,
    AgentLoopError,
    BackendToolError,
    HarnessConflictError,
    SessionAccessError,
    SessionNotFoundError,
)
from app.llm.chat_completions import ChatCompletionsModel
from app.llm.mock import MockOrderingModel
from app.memory.coordinator import RedisSessionCoordinator, SessionCoordinator
from app.memory.extractor import NoOpMemoryExtractor, ToolMemoryExtractor
from app.memory.in_memory import InMemorySessionStore
from app.memory.long_term import BackendUserMemoryStore
from app.memory.redis_store import RedisSessionStore
from app.tools.executor import ToolExecutor


def create_app(
    *,
    settings: Settings | None = None,
    orchestrator: AgentOrchestrator | None = None,
    backend_client: OnlineOrderBackendClient | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if orchestrator is not None:
            app.state.orchestrator = orchestrator
            app.state.backend_client = backend_client
            yield
            return

        from app.evaluation.mock_backend import DemoBackend

        if active_settings.demo_backend:
            demo = DemoBackend()
            transport = httpx.MockTransport(demo.handle)
        else:
            transport = None
        http_client = httpx.AsyncClient(
            base_url=active_settings.onlineorder_backend_url,
            timeout=active_settings.backend_timeout_seconds,
            transport=transport,
        )
        if active_settings.session_backend == "redis":
            redis = Redis.from_url(
                active_settings.redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            session_store = RedisSessionStore(redis)
            coordinator = RedisSessionCoordinator(
                redis, lease_seconds=active_settings.agent_turn_timeout_seconds + 30
            )
        else:
            session_store = InMemorySessionStore()
            coordinator = SessionCoordinator()

        active_backend_client = OnlineOrderBackendClient(
            http_client,
            read_retries=active_settings.backend_read_retries,
        )
        app.state.backend_client = active_backend_client
        model = (
            MockOrderingModel()
            if active_settings.llm_provider == "mock"
            else ChatCompletionsModel(active_settings)
        )
        app.state.orchestrator = AgentOrchestrator(
            model=model,
            tool_executor=ToolExecutor(active_backend_client),
            session_store=session_store,
            coordinator=coordinator,
            session_ttl_seconds=active_settings.session_ttl_seconds,
            recent_message_limit=active_settings.session_recent_message_limit,
            max_tool_steps=active_settings.agent_max_tool_steps,
            user_memory_store=BackendUserMemoryStore(active_backend_client),
            memory_extractor=(
                ToolMemoryExtractor(model)
                if active_settings.memory_extraction_enabled
                and active_settings.llm_provider != "mock"
                else NoOpMemoryExtractor()
            ),
            long_term_memory_limit=active_settings.long_term_memory_limit,
            turn_timeout_seconds=active_settings.agent_turn_timeout_seconds,
            memory_timeout_seconds=active_settings.memory_timeout_seconds,
            action_ttl_seconds=active_settings.action_ttl_seconds,
            pending_ttl_seconds=active_settings.pending_action_ttl_seconds,
            reference_ttl_seconds=active_settings.result_reference_ttl_seconds,
            context_char_budget=active_settings.context_char_budget,
        )
        try:
            yield
        finally:
            await http_client.aclose()
            await session_store.close()
            if hasattr(model, "close"):
                await model.close()

    app = FastAPI(
        title="OnlineOrder Agent",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(router)

    @app.exception_handler(AgentConfigurationError)
    async def configuration_error(
        _request: Request,
        exception: AgentConfigurationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"code": "AGENT_NOT_CONFIGURED", "message": str(exception)}
        )

    @app.exception_handler(SessionAccessError)
    async def session_access_error(
        _request: Request,
        exception: SessionAccessError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=403, content={"code": "SESSION_FORBIDDEN", "message": str(exception)}
        )

    @app.exception_handler(SessionNotFoundError)
    async def session_not_found_error(
        _request: Request,
        exception: SessionNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404, content={"code": "SESSION_NOT_FOUND", "message": str(exception)}
        )

    @app.exception_handler(HarnessConflictError)
    async def harness_conflict(_request: Request, exception: HarnessConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409, content={"code": exception.code, "message": str(exception)}
        )

    @app.exception_handler(BackendToolError)
    async def backend_error(_request: Request, exception: BackendToolError) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"code": exception.code, "message": exception.message}
        )

    @app.exception_handler(RedisError)
    async def storage_error(_request: Request, _exception: RedisError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={
                "code": "SESSION_STORE_UNAVAILABLE",
                "message": "Session storage is unavailable. Inspect the action before retrying a cart change.",
            },
        )

    @app.exception_handler(AgentLoopError)
    async def loop_error(
        _request: Request,
        exception: AgentLoopError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"code": "AGENT_LOOP_STOPPED", "message": str(exception)}
        )

    @app.exception_handler(openai.APIError)
    async def openai_error(_request: Request, _exception: openai.APIError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "code": "MODEL_PROVIDER_ERROR",
                "message": "The language model provider could not complete the request.",
            },
        )

    return app


app = create_app()
