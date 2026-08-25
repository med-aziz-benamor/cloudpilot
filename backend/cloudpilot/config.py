"""Application configuration.

All settings are type-safe and loaded from the environment via pydantic-settings.
Nothing in the codebase reads ``os.environ`` directly — everything flows through
the singleton ``settings`` object so configuration is validated once at startup.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The insecure placeholder shipped as the dev default for signing secrets. Kept as a
# single named constant so the field defaults and the production guard below can never
# drift apart.
_INSECURE_SECRET_DEFAULT = "change-me-in-production-min-32-chars-long-please"


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
    APP_SECRET_KEY: str = _INSECURE_SECRET_DEFAULT
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
    JWT_SECRET: str = _INSECURE_SECRET_DEFAULT
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_AUDIENCE: str = "cloudpilot"
    FERNET_MASTER_KEY: str = ""
    BCRYPT_ROUNDS: int = 12

    # Brute-force protection
    LOGIN_MAX_ATTEMPTS_PER_IP: int = 5
    LOGIN_WINDOW_SECONDS: int = 300
    LOGIN_MAX_ATTEMPTS_PER_EMAIL: int = 10
    LOGIN_LOCKOUT_SECONDS: int = 900

    # ─── AI ────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"
    CHROMADB_HOST: str = "localhost"
    CHROMADB_PORT: int = 8000
    CHROMADB_COLLECTION: str = "cloudpilot_docs_v1"
    OPENAI_API_KEY: str = ""
    # The system prompt asks for answers under ~250 words; 2048 tokens of headroom
    # just let a small local model ramble past the timeout.
    LLM_MAX_OUTPUT_TOKENS: int = 512
    # A 3B model doing RAG on CPU needs far longer than a hosted API would. Too low a
    # timeout silently routes every answer to the offline fallback.
    LLM_TIMEOUT_SECONDS: int = 180

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

    @model_validator(mode="after")
    def _guard_secrets(self) -> Settings:
        """Fail fast on insecure secrets.

        A malformed ``FERNET_MASTER_KEY`` is always wrong, so it is rejected in
        every environment. The signing-secret and missing-key checks apply only
        when ``APP_ENV=production`` — dev/demo keeps booting on the placeholders.
        """
        # A set-but-invalid Fernet key would otherwise blow up later, deep inside
        # credential encryption, with a far less obvious error. Catch it at startup.
        if self.FERNET_MASTER_KEY:
            from cryptography.fernet import Fernet

            try:
                Fernet(self.FERNET_MASTER_KEY.encode())
            except Exception as exc:  # noqa: BLE001 — surface any parse failure the same way
                raise ValueError(
                    "FERNET_MASTER_KEY is not a valid Fernet key (url-safe base64 "
                    "of 32 bytes). Generate one with:\n"
                    "  python -c 'from cryptography.fernet import Fernet; "
                    "print(Fernet.generate_key().decode())'"
                ) from exc

        if not self.is_production:
            return self

        insecure: list[str] = []
        if not self.JWT_SECRET or self.JWT_SECRET == _INSECURE_SECRET_DEFAULT:
            insecure.append("JWT_SECRET")
        if not self.APP_SECRET_KEY or self.APP_SECRET_KEY == _INSECURE_SECRET_DEFAULT:
            insecure.append("APP_SECRET_KEY")
        # Empty FERNET_MASTER_KEY would silently fall back to a key derived from a
        # source-code constant — anyone with the repo could decrypt stored cloud
        # credentials. Refuse to run this way in production.
        if not self.FERNET_MASTER_KEY:
            insecure.append("FERNET_MASTER_KEY")

        if insecure:
            raise ValueError(
                "Refusing to start with APP_ENV=production while these secrets are "
                f"unset or left at their insecure defaults: {', '.join(insecure)}. "
                "Set each to a strong, unique value via the environment before "
                "deploying."
            )
        return self

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
        without manual key generation. Production MUST set ``FERNET_MASTER_KEY`` —
        the ``_guard_secrets`` validator refuses to start otherwise, so the fallback
        below is unreachable in production; the guard here is defence in depth.
        """
        if self.FERNET_MASTER_KEY:
            return self.FERNET_MASTER_KEY.encode()
        if self.is_production:  # pragma: no cover — _guard_secrets already blocks this
            raise RuntimeError(
                "FERNET_MASTER_KEY must be set in production; refusing to use the "
                "insecure dev fallback key."
            )
        # Deterministic dev fallback (base64url 32 bytes). Never use in production.
        import base64

        return base64.urlsafe_b64encode(b"cloudpilot-dev-fallback-key-32by")


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()


settings = get_settings()
