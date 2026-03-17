from functools import cached_property

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Gmail Cleanup AI"
    environment: str = "development"
    debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_url: str = "http://localhost:5173"
    secret_key: str
    database_url: str
    redis_url: str

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"
    google_oauth_scopes: str = (
        "openid,email,profile,https://www.googleapis.com/auth/gmail.modify"
    )

    embedding_provider: str = "fake"
    embedding_model: str = "fake-hash-v1"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_dimension: int = 16

    llm_provider: str = "none"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"

    sync_page_size: int = Field(default=25, ge=1, le=100)
    similarity_limit_default: int = Field(default=5, ge=1, le=20)
    token_expiry_minutes: int = Field(default=60, ge=5, le=1440)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off", "release"}:
                return False
        return False

    @cached_property
    def google_scopes(self) -> list[str]:
        return [scope.strip() for scope in self.google_oauth_scopes.split(",") if scope.strip()]


settings = Settings()
