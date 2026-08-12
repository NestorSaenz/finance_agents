"""Application configuration using Pydantic Settings."""

from typing import Annotated, Any, Literal

from pydantic import AnyUrl, BeforeValidator, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors(v: Any) -> list[str] | str:
    """Parse CORS origins from string or list."""
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # ============================================
    # API Configuration
    # ============================================
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    PROJECT_NAME: str = "Safi"
    # Deployed code version (git SHA), set by the CI deploy; tags every Langfuse
    # trace so behavior can be correlated to a release. Empty on local runs.
    RELEASE: str = ""

    # Demo user UUID used until real auth (JWT) is wired. Must be a real user in
    # the `users` table (create one in Supabase Auth, then paste its UUID here).
    DEMO_USER_ID: str = ""

    # How many recent conversation messages to feed the LLM as context.
    CHAT_HISTORY_LIMIT: int = 10

    # Shared secret guarding POST /recurring/run (the daily materialization job).
    # A Cloud Scheduler job must send it in the X-Recurring-Secret header. Empty
    # (the default) fails the endpoint closed, so it can never run unprotected.
    RECURRING_RUN_SECRET: str = ""

    # IANA timezone in which recurring schedules are evaluated. Day-of-month
    # charges must fire on the user's LOCAL calendar day, so "today" and the daily
    # run date are computed in this zone (not UTC) — otherwise a LatAm "day 30"
    # could fire a day early near midnight.
    RECURRING_TIMEZONE: str = "America/Bogota"

    # ============================================
    # Rate Limiting (chat cost / abuse control)
    # ============================================
    # Caps POST /chat per authenticated user. Reads (dashboard, etc.) are unaffected.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_CHAT_PER_MINUTE: int = 10  # Burst guard: every turn (text or image).
    RATE_LIMIT_CHAT_PER_DAY: int = 100  # Daily text turns.
    RATE_LIMIT_IMAGES_PER_DAY: int = 10  # Daily image turns (heavier: Gemini vision).

    BACKEND_CORS_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = []

    @computed_field  # type: ignore[prop-decorator]  # pydantic computed_field on property
    @property
    def all_cors_origins(self) -> list[str]:
        """Get all CORS origins as strings."""
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS]

    # ============================================
    # Supabase Configuration
    # ============================================
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""  # Secret/service key used by the trusted backend (bypasses RLS)
    SUPABASE_SERVICE_ROLE_KEY: str = ""  # Service role for admin operations
    SUPABASE_ANON_KEY: str = ""  # Publishable/anon key for user auth (signup/login/JWT)

    # ============================================
    # LLM Provider Selection
    # ============================================
    # "vertex": Vertex AI Gemini (primary, GCP credits + ADC) | "groq": fallback
    LLM_PROVIDER: Literal["vertex", "groq"] = "vertex"
    # When true, LLM calls fall back through a chain (same-provider rescue +
    # cross-provider Groq) if the primary model errors/overloads.
    LLM_FALLBACK_ENABLED: bool = True

    # ============================================
    # Groq Configuration (LLM - cross-provider fallback)
    # ============================================
    GROQ_API_KEY: str = ""
    GROQ_MODEL_SIMPLE: str = "llama-3.3-70b-versatile"
    GROQ_MODEL_COMPLEX: str = "llama-3.3-70b-versatile"

    # ============================================
    # Embeddings (Vertex AI Gemini, 768 dims)
    # ============================================
    EMBEDDING_DIMENSION: int = 768

    # ============================================
    # Google Cloud / Vertex AI Configuration
    # ============================================
    # LLM + embeddings run on Vertex (auth via ADC / service account).
    GCP_PROJECT: str = ""
    GCP_LOCATION: str = "us-central1"
    VERTEX_EMBED_MODEL: str = "gemini-embedding-001"  # Multilingual, configurable dims
    VERTEX_LLM_MODEL_SIMPLE: str = "gemini-2.5-flash-lite"  # Fast classification/categorization
    VERTEX_LLM_MODEL_COMPLEX: str = "gemini-2.5-flash"  # Analysis, planning, tools

    # ============================================
    # Langfuse Configuration
    # ============================================
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    # ============================================
    # Optional: Sentry
    # ============================================
    SENTRY_DSN: str = ""

    # ============================================
    # Optional: Redis
    # ============================================
    REDIS_URL: str = ""

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == "production"

    def has_langfuse(self) -> bool:
        """Check if Langfuse is configured."""
        return bool(self.LANGFUSE_PUBLIC_KEY and self.LANGFUSE_SECRET_KEY)


# Global settings instance
settings = Settings()
