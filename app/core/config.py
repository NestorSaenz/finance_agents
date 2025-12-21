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
    PROJECT_NAME: str = "FinanceGPT"

    BACKEND_CORS_ORIGINS: Annotated[list[AnyUrl] | str, BeforeValidator(parse_cors)] = []

    @computed_field
    @property
    def all_cors_origins(self) -> list[str]:
        """Get all CORS origins as strings."""
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS]

    # ============================================
    # Supabase Configuration
    # ============================================
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""  # Anon key for client-side
    SUPABASE_SERVICE_ROLE_KEY: str = ""  # Service role for admin operations

    # ============================================
    # Groq Configuration (Primary LLM - Free tier)
    # ============================================
    GROQ_API_KEY: str = ""
    GROQ_MODEL_SIMPLE: str = "llama-3.1-8b-instant"  # Fast, 14.4K req/day
    GROQ_MODEL_COMPLEX: str = "llama-3.3-70b-versatile"  # Powerful, 1K req/day

    # ============================================
    # Cohere Configuration (Embeddings)
    # ============================================
    COHERE_API_KEY: str = ""
    COHERE_EMBED_MODEL: str = "embed-multilingual-v3.0"
    COHERE_LLM_MODEL: str = "command-r-plus"  # Fallback LLM
    EMBEDDING_DIMENSION: int = 1024

    # ============================================
    # Gemini Configuration (Google AI - Pro quality)
    # ============================================
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_SIMPLE: str = "gemini-1.5-flash"  # Fast, cheap
    GEMINI_MODEL_COMPLEX: str = "gemini-1.5-pro"  # Best quality

    # ============================================
    # Pinecone Configuration
    # ============================================
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX: str = "financegpt-transactions"
    PINECONE_ENVIRONMENT: str = "us-east-1"

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
