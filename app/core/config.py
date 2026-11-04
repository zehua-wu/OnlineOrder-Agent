from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    openai_api_key: str | None = Field(default=None, repr=False)
    openai_model: str = "gpt-5-nano"
    llm_provider: Literal["qwen", "deepseek", "openai", "mock"] = "qwen"
    llm_api_key: str | None = Field(default=None, repr=False)
    qwen_api_key: str | None = Field(default=None, repr=False)
    deepseek_api_key: str | None = Field(default=None, repr=False)
    llm_model: str | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: float = Field(default=20, gt=0, le=60)
    llm_max_retries: int = Field(default=1, ge=0, le=2)
    llm_max_output_tokens: int = Field(default=1200, ge=128, le=8192)
    demo_backend: bool = False
    memory_extraction_enabled: bool = True
    memory_timeout_seconds: float = Field(default=5, gt=0, le=15)
    agent_turn_timeout_seconds: float = Field(default=75, gt=0, le=180)
    action_ttl_seconds: int = Field(default=604800, ge=3600)
    pending_action_ttl_seconds: int = Field(default=300, ge=30, le=1800)
    result_reference_ttl_seconds: int = Field(default=900, ge=30)
    context_char_budget: int = Field(default=30000, ge=8000, le=100000)

    onlineorder_backend_url: str = "http://localhost:8080"
    backend_timeout_seconds: float = Field(default=5.0, gt=0)
    backend_read_retries: int = Field(default=1, ge=0, le=3)

    session_backend: Literal["memory", "redis"] = "memory"
    session_ttl_seconds: int = Field(default=14_400, ge=60)
    session_recent_message_limit: int = Field(default=12, ge=2, le=100)
    long_term_memory_limit: int = Field(default=50, ge=1, le=100)
    redis_url: str = "redis://localhost:6379/0"

    agent_max_tool_steps: int = Field(default=5, ge=1, le=20)
    cors_origins: str = "http://localhost:3000"

    @model_validator(mode="after")
    def validate_runtime(self) -> "Settings":
        if self.app_env == "production" and (self.demo_backend or self.llm_provider == "mock"):
            raise ValueError("Mock model/backend is forbidden in production")
        if self.app_env == "production" and self.session_backend != "redis":
            raise ValueError("Production requires Redis sessions, user locks and journals")
        if self.action_ttl_seconds < self.session_ttl_seconds:
            raise ValueError("action_ttl_seconds must cover session_ttl_seconds")
        return self

    @property
    def model_name(self) -> str:
        return (
            self.llm_model
            or {
                "qwen": "qwen-plus",
                "deepseek": "deepseek-chat",
                "openai": self.openai_model,
                "mock": "mock",
            }[self.llm_provider]
        )

    @property
    def model_api_key(self) -> str | None:
        return (
            self.llm_api_key
            or {
                "qwen": self.qwen_api_key,
                "deepseek": self.deepseek_api_key,
                "openai": self.openai_api_key,
                "mock": None,
            }[self.llm_provider]
        )

    @property
    def model_base_url(self) -> str:
        return (
            self.llm_base_url
            or {
                "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "deepseek": "https://api.deepseek.com/v1",
                "openai": "https://api.openai.com/v1",
                "mock": "http://mock.invalid",
            }[self.llm_provider]
        )

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
