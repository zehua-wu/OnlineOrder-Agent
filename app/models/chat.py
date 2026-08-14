from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(min_length=1, max_length=4_000)
    session_id: UUID | None = Field(default=None, alias="sessionId")

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message cannot be blank")
        return value


class MenuItemCard(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    position: int = Field(ge=1)
    menu_item_id: str = Field(alias="menuItemId")
    name: str
    description: str | None = None
    ingredient_summary: str | None = Field(default=None, alias="ingredientSummary")
    restaurant_id: str | None = Field(default=None, alias="restaurantId")
    restaurant_name: str | None = Field(default=None, alias="restaurantName")
    price: float | None = None
    image_url: str | None = Field(default=None, alias="imageUrl")
    category: str | None = None
    cuisine_type: str | None = Field(default=None, alias="cuisineType")
    available_quantity: int | None = Field(default=None, alias="availableQuantity")
    primary_protein: str | None = Field(default=None, alias="primaryProtein")
    spicy_level: int | None = Field(default=None, alias="spicyLevel")
    sweetness_level: int | None = Field(default=None, alias="sweetnessLevel")
    vegetarian: bool | None = None
    caffeinated: bool | None = None
    serving_temperature: str | None = Field(default=None, alias="servingTemperature")


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str = Field(alias="sessionId")
    answer: str
    tool_steps: int = Field(alias="toolSteps", ge=0)
    cards: list[MenuItemCard] = Field(default_factory=list)
    total_results: int = Field(default=0, alias="totalResults", ge=0)
    has_more: bool = Field(default=False, alias="hasMore")


class SearchCardsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    cards: list[MenuItemCard] = Field(default_factory=list)
    total_results: int = Field(alias="totalResults", ge=0)
    next_offset: int = Field(alias="nextOffset", ge=0)
    has_more: bool = Field(alias="hasMore")
