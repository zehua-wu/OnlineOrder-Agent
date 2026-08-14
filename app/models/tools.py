from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SearchFilterName = Literal[
    "keyword",
    "cuisine_type",
    "category",
    "primary_protein",
    "max_spicy_level",
    "max_sweetness_level",
    "vegetarian",
    "caffeinated",
    "serving_temperature",
    "min_price",
    "max_price",
]


class SearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    FILTER_FIELDS: ClassVar[tuple[str, ...]] = (
        "keyword",
        "cuisine_type",
        "category",
        "primary_protein",
        "max_spicy_level",
        "max_sweetness_level",
        "vegetarian",
        "caffeinated",
        "serving_temperature",
        "min_price",
        "max_price",
        "limit",
    )

    keyword: str | None = Field(default=None, max_length=100)
    cuisine_type: Literal[
        "AMERICAN", "CHINESE", "MEXICAN", "ITALIAN", "JAPANESE",
        "KOREAN", "INDIAN", "THAI", "MEDITERRANEAN", "OTHER",
    ] | None = None
    category: str | None = Field(default=None, max_length=50)
    primary_protein: Literal[
        "CHICKEN", "BEEF", "PORK", "LAMB", "FISH", "SHRIMP",
        "TOFU", "EGG", "NONE", "OTHER",
    ] | None = None
    max_spicy_level: int | None = Field(default=None, ge=0, le=4)
    max_sweetness_level: int | None = Field(default=None, ge=0, le=4)
    vegetarian: bool | None = None
    caffeinated: bool | None = None
    serving_temperature: Literal["HOT", "COLD", "ROOM"] | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    limit: int | None = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def validate_price_range(self) -> "SearchFilters":
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price cannot be greater than max_price")
        return self

    def to_backend_payload(self) -> dict[str, object]:
        aliases = {
            "cuisine_type": "cuisineType",
            "primary_protein": "primaryProtein",
            "max_spicy_level": "maxSpicyLevel",
            "max_sweetness_level": "maxSweetnessLevel",
            "serving_temperature": "servingTemperature",
            "min_price": "minPrice",
            "max_price": "maxPrice",
        }
        payload = {
            field: getattr(self, field)
            for field in self.FILTER_FIELDS
            if getattr(self, field) is not None
        }
        return {aliases.get(key, key): value for key, value in payload.items()}


class SearchMenuArgs(SearchFilters):
    start_new_search: bool = False
    clear_filters: list[SearchFilterName] = Field(default_factory=list)


class SelectSearchResultArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1, le=100)
