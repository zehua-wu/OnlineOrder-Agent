from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import openai
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.agent.orchestrator import AgentOrchestrator
from app.api.routes import router
from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    AgentConfigurationError,
    AgentLoopError,
    SessionAccessError,
    SessionNotFoundError,
)
from app.llm.openai_responses import OpenAIResponsesModel
from app.memory.coordinator import SessionCoordinator
from app.memory.extractor import NoOpMemoryExtractor, OpenAIMemoryExtractor
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

        http_client = httpx.AsyncClient(
            base_url=active_settings.onlineorder_backend_url,
            timeout=active_settings.backend_timeout_seconds,
        )
        if active_settings.session_backend == "redis":
            redis = Redis.from_url(active_settings.redis_url, decode_responses=True)
            session_store = RedisSessionStore(redis)
        else:
            session_store = InMemorySessionStore()

        active_backend_client = OnlineOrderBackendClient(
            http_client,
            read_retries=active_settings.backend_read_retries,
        )
        app.state.backend_client = active_backend_client
        app.state.orchestrator = AgentOrchestrator(
            model=OpenAIResponsesModel(
                api_key=active_settings.openai_api_key,
                model=active_settings.openai_model,
            ),
            tool_executor=ToolExecutor(active_backend_client),
            session_store=session_store,
            coordinator=SessionCoordinator(),
            session_ttl_seconds=active_settings.session_ttl_seconds,
            recent_message_limit=active_settings.session_recent_message_limit,
            max_tool_steps=active_settings.agent_max_tool_steps,
            user_memory_store=BackendUserMemoryStore(active_backend_client),
            memory_extractor=(
                OpenAIMemoryExtractor(
                    api_key=active_settings.openai_api_key,
                    model=active_settings.openai_model,
                )
                if active_settings.openai_api_key
                else NoOpMemoryExtractor()
            ),
            long_term_memory_limit=active_settings.long_term_memory_limit,
        )
        try:
            yield
        finally:
            await http_client.aclose()
            await session_store.close()

    app = FastAPI(
        title="OnlineOrder Agent",
        version="0.1.0",
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
        return JSONResponse(status_code=503, content={"code": "AGENT_NOT_CONFIGURED", "message": str(exception)})

    @app.exception_handler(SessionAccessError)
    async def session_access_error(
        _request: Request,
        exception: SessionAccessError,
    ) -> JSONResponse:
        return JSONResponse(status_code=403, content={"code": "SESSION_FORBIDDEN", "message": str(exception)})

    @app.exception_handler(SessionNotFoundError)
    async def session_not_found_error(
        _request: Request,
        exception: SessionNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(status_code=404, content={"code": "SESSION_NOT_FOUND", "message": str(exception)})

    @app.exception_handler(AgentLoopError)
    async def loop_error(
        _request: Request,
        exception: AgentLoopError,
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"code": "AGENT_LOOP_STOPPED", "message": str(exception)})

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
