from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: str = Field(default="openrouter", alias="LLM_PROVIDER")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", alias="OPENAI_BASE_URL"
    )

    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="google/gemma-4-31b-it:free", alias="OPENROUTER_MODEL"
    )
    openrouter_models: str = Field(
        default=(
            "google/gemma-4-31b-it:free,"
            "arcee-ai/trinity-large-preview:free,"
            "google/gemma-4-26b-a4b-it:free,"
            "openai/gpt-oss-120b:free,"
            "google/gemma-3-4b-it:free"
        ),
        alias="OPENROUTER_MODELS",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_http_referer: str = Field(
        default="http://localhost:8000", alias="OPENROUTER_HTTP_REFERER"
    )
    openrouter_app_title: str = Field(default="UI Bot", alias="OPENROUTER_APP_TITLE")

    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")

    database_path: Path = Field(
        default=Path("./data/ui_bot.sqlite3"), alias="UI_BOT_DATABASE_PATH"
    )
    headless: bool = Field(default=True, alias="UI_BOT_HEADLESS")
    browser_timeout_ms: int = Field(default=15000, alias="UI_BOT_BROWSER_TIMEOUT_MS")
    allowed_origins: str = Field(
        default="http://localhost:8000", alias="UI_BOT_ALLOWED_ORIGINS"
    )

    @field_validator("llm_provider")
    @classmethod
    def normalize_provider(cls, value: str) -> str:
        return value.strip().lower()

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin]

    @property
    def openrouter_model_list(self) -> list[str]:
        configured = [model.strip() for model in self.openrouter_models.split(",")]
        configured = [model for model in configured if model]
        if self.openrouter_model and self.openrouter_model not in configured:
            return [self.openrouter_model, *configured]
        return configured


@lru_cache
def get_settings() -> Settings:
    return Settings()
