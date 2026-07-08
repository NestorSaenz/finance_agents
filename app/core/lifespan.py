"""Application lifespan management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.shared.dependencies import close_database, init_database
from app.src.auth.dependencies import close_auth, init_auth

from .config import settings
from .logging import get_logger, setup_logging
from .observability import flush_observability, init_observability

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager.

    Handles startup and shutdown events for the application.

    Args:
        app: FastAPI application instance

    Yields:
        None during application runtime
    """
    # ============================================
    # STARTUP
    # ============================================
    setup_logging()
    logger.info(
        "Starting FinanceGPT",
        environment=settings.ENVIRONMENT,
        project=settings.PROJECT_NAME,
    )

    # Validate required settings
    _validate_settings()

    # Initialize database connection
    if settings.SUPABASE_URL and settings.SUPABASE_KEY:
        await init_database()
        logger.info("Database connection initialized")

    # Initialize the auth service (Supabase Auth via anon key)
    await init_auth()

    # Initialize observability (Langfuse tracing); no-op if not configured.
    init_observability()

    logger.info("Application startup complete")

    yield

    # ============================================
    # SHUTDOWN
    # ============================================
    logger.info("Shutting down FinanceGPT")

    # Cleanup connections
    await close_database()
    await close_auth()
    flush_observability()
    logger.info("Database connection closed")

    logger.info("Application shutdown complete")


def _validate_settings() -> None:
    """Validate that the settings for the active providers are configured."""
    missing = []

    if not settings.SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not settings.SUPABASE_KEY:
        missing.append("SUPABASE_KEY")
    # Vertex (LLM primary + embeddings) authenticates via ADC but needs a project.
    if not settings.GCP_PROJECT:
        missing.append("GCP_PROJECT")
    # Groq is the cross-provider fallback when enabled.
    if settings.LLM_FALLBACK_ENABLED and not settings.GROQ_API_KEY:
        missing.append("GROQ_API_KEY")

    if missing and settings.ENVIRONMENT != "local":
        logger.warning(
            "Missing required settings",
            missing_settings=missing,
        )
