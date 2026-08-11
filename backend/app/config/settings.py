"""
Centralized application configuration.

All environment variables are declared here and nowhere else. This is the
single source of truth for config — no os.getenv() calls should appear
anywhere else in the codebase. Pydantic Settings gives us validation
(fails fast on startup if a required var is missing) and type coercion.
"""
from functools import lru_cache

import json

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = "WhatsApp AI SaaS"
    environment: str = Field(default="development")  # development | production
    log_level: str = Field(default="INFO")
    port: int = Field(default=8000)

    # --- Dashboard API authentication ---
    auth_disabled: bool = Field(default=True)
    admin_api_key: str | None = Field(default=None)
    # JSON object: {"api-key": ["tenant_object_id", ...]}
    tenant_api_keys_json: str = Field(default="{}")

    # --- CORS ---
    # Comma-separated origins in the env var, e.g. "https://app.example.com,http://localhost:5173"
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:4173,https://krid-kaws-1.onrender.com"
    )
    cors_allowed_origin_regex: str | None = Field(default=r"https://.*\.onrender\.com")

    # --- MongoDB ---
    mongodb_uri: str = Field(..., description="MongoDB Atlas connection string")
    mongodb_db_name: str = Field(default="whatsapp_saas")
    allow_in_memory_database: bool = Field(default=True)

    # --- Gemini ---
    gemini_api_key: str = Field(..., description="Gemini API key")
    gemini_model: str = Field(default="gemini-2.5-flash")
    gemini_vision_model: str = Field(default="gemini-2.5-flash")

    # --- Meta WhatsApp Cloud API ---
    meta_app_secret: str = Field(..., description="Used to validate X-Hub-Signature-256")
    meta_webhook_verify_token: str = Field(..., description="Used for GET webhook verification challenge")
    meta_access_token: str = Field(..., description="Permanent/long-lived Graph API access token")
    # Optional phone-number-specific tokens: {"phone_number_id": "token"}
    meta_access_tokens_json: str = Field(default="{}")
    meta_phone_number_id: str = Field(..., description="Default WhatsApp Business phone number ID")
    meta_graph_api_version: str = Field(default="v20.0")

    # --- Typing indicator heartbeat ---
    typing_heartbeat_interval_seconds: int = Field(default=20)

    # --- Sentiment / handover threshold ---
    # sentiment_score is expected in range [0.0, 1.0], where higher = more frustrated.
    handover_sentiment_threshold: float = Field(default=0.75)

    # --- Durable job worker ---
    job_poll_interval_seconds: float = Field(default=0.5, ge=0.1)
    job_lease_seconds: int = Field(default=120, ge=10)
    job_max_attempts: int = Field(default=5, ge=1)
    broadcast_jobs_per_minute: int = Field(default=10, ge=1)

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def graph_api_base_url(self) -> str:
        return f"https://graph.facebook.com/{self.meta_graph_api_version}"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def tenant_api_keys(self) -> dict[str, list[str]]:
        parsed = json.loads(self.tenant_api_keys_json)
        if not isinstance(parsed, dict) or not all(
            isinstance(key, str) and isinstance(value, list) and all(isinstance(v, str) for v in value)
            for key, value in parsed.items()
        ):
            raise ValueError("TENANT_API_KEYS_JSON must map API keys to tenant ID lists")
        return parsed

    @property
    def meta_access_tokens(self) -> dict[str, str]:
        parsed = json.loads(self.meta_access_tokens_json)
        if not isinstance(parsed, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()):
            raise ValueError("META_ACCESS_TOKENS_JSON must map phone number IDs to access tokens")
        return parsed

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.is_production:
            if self.auth_disabled:
                raise ValueError("AUTH_DISABLED must be false in production")
            if not self.admin_api_key or len(self.admin_api_key) < 32:
                raise ValueError("ADMIN_API_KEY must contain at least 32 characters in production")
            if self.cors_allowed_origin_regex and ".*" in self.cors_allowed_origin_regex:
                raise ValueError("Wildcard CORS origin regex is not allowed in production")
            if self.allow_in_memory_database:
                raise ValueError("ALLOW_IN_MEMORY_DATABASE must be false in production")
        self.tenant_api_keys
        self.meta_access_tokens
        return self


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings accessor. Use this everywhere instead of instantiating
    Settings() directly, so we only parse/validate env vars once per process.
    """
    return Settings()
