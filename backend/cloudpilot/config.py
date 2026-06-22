"""Application configuration.

All settings are type-safe and loaded from the environment via pydantic-settings.
Nothing in the codebase reads ``os.environ`` directly — everything flows through
the singleton ``settings`` object so configuration is validated once at startup.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ─── App ───────────────────────────────────────────────
    APP_ENV: str = "development"
    APP_SECRET_KEY: str = "change-me-in-production-min-32-chars-long-please"
    DEBUG: bool = True
    APP_NAME: str = "CloudPilot"
    API_V1_PREFIX: str = "/api/v1"

    # ─── Database ──────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://cp:cp@localhost:5432/cloudpilot"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # ─── Redis ─────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ─── Security ──────────────────────────────────────────
    JWT_SECRET: str = "change-me-in-production-min-32-chars-long-please"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_AUDIENCE: str = "cloudpilot"
    FERNET_MASTER_KEY: str = ""
    BCRYPT_ROUNDS: int = 12

    # Brute-force protection
    LOGIN_MAX_ATTEMPTS_PER_IP: int = 5
    LOGIN_WINDOW_SECONDS: int = 300
    LOGIN_LOCKOUT_SECONDS: int = 900

    # ─── AI ────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:4b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    CHROMADB_HOST: str = "localhost"
    CHROMADB_PORT: int = 8000
    CHROMADB_COLLECTION: str = "cloudpilot_docs_v1"
    OPENAI_API_KEY: str = ""
    LLM_MAX_OUTPUT_TOKENS: int = 2048
    LLM_TIMEOUT_SECONDS: int = 30

    # ─── Cloud Providers ───────────────────────────────────
    DEMO_MODE: bool = True
    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    AZURE_SUBSCRIPTION_ID: str = ""
    AWS_ACCOUNT_ID: str = ""
    AWS_ROLE_ARN: str = ""
    AWS_EXTERNAL_ID: str = ""
    GCP_PROJECT_ID: str = ""
    GCP_SERVICE_ACCOUNT_JSON: str = ""

    # ─── CORS ──────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # ─── Caching TTLs (seconds) ────────────────────────────
    CACHE_DASHBOARD_TTL: int = 300
    CACHE_PRICING_TTL: int = 604_800  # one week

    @field_validator("CORS_ORIGINS")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS origins parsed into a list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() == "production"

    @property
    def fernet_key_bytes(self) -> bytes:
        """The Fernet master key as bytes.

        In demo/dev a deterministic fallback key is derived so the platform boots
        without manual key generation. Production MUST set ``FERNET_MASTER_KEY``.
        """
        if self.FERNET_MASTER_KEY:
            return self.FERNET_MASTER_KEY.encode()
        # Deterministic dev fallback (base64url 32 bytes). Never use in production.
        import base64

        return base64.urlsafe_b64encode(b"cloudpilot-dev-fallback-key-32by")


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()


settings = get_settings()
