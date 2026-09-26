from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LongTermMemory(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)


class MemoryMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: Literal["UPSERT", "DELETE"]
    key: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9_.:-]*$",
    )
    value: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_value(self) -> "MemoryMutation":
        if self.operation == "UPSERT" and (self.value is None or not self.value.strip()):
            raise ValueError("value is required for UPSERT memory mutations")
        return self

    def to_backend_payload(self) -> dict[str, str | None]:
        return {
            "operation": self.operation,
            "key": self.key,
            "value": self.value.strip() if self.value is not None else None,
        }


class MemoryExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutations: list[MemoryMutation] = Field(default_factory=list, max_length=5)
