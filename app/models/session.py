from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.tools import SearchFilters


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class SearchResultReference(BaseModel):
    position: int = Field(ge=1)
    menu_item_id: str
    name: str
    description: str | None = None
    ingredient_summary: str | None = None
    restaurant_name: str | None = None
    restaurant_id: str | None = None
    price: float | None = None
    image_url: str | None = None
    category: str | None = None
    cuisine_type: str | None = None
    available_quantity: int | None = None
    primary_protein: str | None = None
    spicy_level: int | None = None
    sweetness_level: int | None = None
    vegetarian: bool | None = None
    caffeinated: bool | None = None
    serving_temperature: str | None = None


class SelectedItem(BaseModel):
    menu_item_id: str
    name: str
    restaurant_name: str | None = None
    price: float | None = None


class ConversationState(BaseModel):
    current_task: Literal["NONE", "MENU_SEARCH"] = "NONE"
    search: SearchFilters = Field(default_factory=SearchFilters)
    last_search_results: list[SearchResultReference] = Field(default_factory=list)
    selected_item: SelectedItem | None = None
    phase: Literal["CHAT", "AWAITING_CONFIRMATION", "CHECKOUT_PROCESSING", "DONE"] = "CHAT"
    pending_action: dict[str, object] | None = None


class ConversationSession(BaseModel):
    session_id: str
    user_id: str | None = None
    # Transitional support for Redis sessions created before stable user IDs.
    owner_fingerprint: str | None = None
    messages: list[ConversationMessage] = Field(default_factory=list)
    state: ConversationState = Field(default_factory=ConversationState)
    summary: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
