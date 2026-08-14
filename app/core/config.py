from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-luna"

    onlineorder_backend_url: str = "http://localhost:8080"
    backend_timeout_seconds: float = Field(default=5.0, gt=0)
    backend_read_retries: int = Field(default=1, ge=0, le=3)

    session_backend: Literal["memory", "redis"] = "memory"
    session_ttl_seconds: int = Field(default=14_400, ge=60)
    session_recent_message_limit: int = Field(default=12, ge=2, le=100)
    redis_url: str = "redis://localhost:6379/0"

    agent_max_tool_steps: int = Field(default=5, ge=1, le=20)
    cors_origins: str = "http://localhost:3000"

    @field_validator("onlineorder_backend_url")
    @classmethod
    def strip_backend_url(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
