"""Application-owned workflow and journal records; no credentials live here."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class PendingAction(BaseModel):
    action_id: str
    kind: Literal["ADD_TO_CART"] = "ADD_TO_CART"
    menu_item_id: str
    restaurant_id: str | None = None
    name: str
    quantity: int = Field(ge=1, le=99)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime


class ToolEvent(BaseModel):
    name: str
    ok: bool
    code: str | None = None
    duration_ms: float = 0


class TurnMetrics(BaseModel):
    duration_ms: float = 0
    model_duration_ms: float = 0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tools: list[ToolEvent] = Field(default_factory=list)


class ActionRecord(BaseModel):
    action: PendingAction
    status: Literal["STARTED", "SUCCEEDED", "FAILED", "UNKNOWN", "ACKNOWLEDGED"]
    cart: dict | None = None
    error_code: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RequestRecord(BaseModel):
    fingerprint: str
    session_id: str
    status: Literal["STARTED", "COMPLETED", "FAILED"] = "STARTED"
    response: dict | None = None
