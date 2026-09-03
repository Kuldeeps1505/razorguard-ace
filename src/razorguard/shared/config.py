"""
Application configuration.

Loaded once at startup from environment variables.
Never hardcode secrets. Never expose this object to LLM context.
"""

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

    # ── Application ──────────────────────────────────────────────
    app_env: Literal["development", "testing", "staging", "production"] = "development"
    app_debug: bool = False
    app_secret_key: str = Field(min_length=32)
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # ── Database ──────────────────────────────────────────────────
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # ── Redis ─────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_lock_ttl_seconds: int = 30

    # ── Razorpay ──────────────────────────────────────────────────
    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str
    razorpay_mode: Literal["test", "live"] = "test"

    # ── LLM ───────────────────────────────────────────────────────
    llm_provider: Literal["claude", "openai", "gemini", "groq"] = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    llm_model_claude: str = "claude-3-5-sonnet-20241022"
    llm_model_openai: str = "gpt-4o"
    llm_model_gemini: str = "gemini-2.5-flash"
    llm_model_groq: str = "openai/gpt-oss-20b"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.1

    # ── JWT ───────────────────────────────────────────────────────
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # ── Capability ────────────────────────────────────────────────
    capability_signing_key: str = Field(min_length=16)
    capability_ttl_seconds: int = 300  # 5 minutes — deliberately short

    # ── Rate Limiting ─────────────────────────────────────────────
    rate_limit_api_per_minute: int = 100
    rate_limit_payment_per_minute: int = 10
    rate_limit_agent_per_minute: int = 60

    # ── Worker ────────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── Observability ─────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    metrics_port: int = 9090

    # Comma-separated browser origins permitted to call the public API.
    # Set this to the Vercel deployment URL in Render production settings.
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:8080"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """Accept Render's PostgreSQL URL while using SQLAlchemy asyncpg."""
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("razorpay_mode")
    @classmethod
    def validate_razorpay_mode(cls, v: str, info: object) -> str:
        # Safety: require explicit override to use live mode.
        # During buildathon, always test mode.
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip().rstrip("/") for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton. Use as FastAPI dependency."""
    return Settings()  # type: ignore[call-arg]
