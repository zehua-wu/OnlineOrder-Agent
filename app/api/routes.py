from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.agent.orchestrator import AgentOrchestrator
from app.clients.onlineorder_backend import OnlineOrderBackendClient
from app.core.exceptions import BackendToolError
from app.models.chat import ChatRequest, ChatResponse, SearchCardsResponse


router = APIRouter()


@dataclass(frozen=True)
class AuthenticatedCustomer:
    user_id: str
    authorization: str


async def require_customer(
    request: Request,
    authorization: str | None,
) -> AuthenticatedCustomer:
    if not authorization or not authorization.startswith("Bearer ") or not authorization[7:].strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Customer login is required to use the ordering assistant.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    backend_client: OnlineOrderBackendClient | None = getattr(
        request.app.state,
        "backend_client",
        None,
    )
    if backend_client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
        )

    try:
        current_user = await backend_client.get_current_user(authorization=authorization)
    except BackendToolError as error:
        if error.status_code in {401, 403}:
            raise HTTPException(
                status_code=error.status_code,
                detail="Customer login is required to use the ordering assistant.",
                headers={"WWW-Authenticate": "Bearer"} if error.status_code == 401 else None,
            ) from error
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable.",
        ) from error

    if str(current_user.get("role", "")).upper() != "CUSTOMER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customer accounts can use the ordering assistant.",
        )

    try:
        user_id = str(UUID(str(current_user.get("id"))))
    except (TypeError, ValueError, AttributeError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service returned an invalid user identity.",
        ) from error

    return AuthenticatedCustomer(user_id=user_id, authorization=authorization)


@router.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/agent/chat", response_model=ChatResponse, tags=["agent"])
async def chat(
    body: ChatRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ChatResponse:
    customer = await require_customer(request, authorization)
    orchestrator: AgentOrchestrator = request.app.state.orchestrator
    return await orchestrator.chat(
        message=body.message.strip(),
        session_id=str(body.session_id) if body.session_id else None,
        user_id=customer.user_id,
        authorization=customer.authorization,
    )


@router.get(
    "/agent/sessions/{session_id}/cards",
    response_model=SearchCardsResponse,
    tags=["agent"],
)
async def get_search_cards(
    session_id: UUID,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=10)] = 3,
) -> SearchCardsResponse:
    customer = await require_customer(request, authorization)
    orchestrator: AgentOrchestrator = request.app.state.orchestrator
    return await orchestrator.get_search_cards(
        session_id=str(session_id),
        user_id=customer.user_id,
        authorization=customer.authorization,
        offset=offset,
        limit=limit,
    )
