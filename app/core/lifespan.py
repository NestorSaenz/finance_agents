"""Application lifespan management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.shared.dependencies import close_database, init_database

from .config import settings
from .logging import get_logger, setup_logging

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

    logger.info("Application startup complete")

    yield

    # ============================================
    # SHUTDOWN
    # ============================================
    logger.info("Shutting down FinanceGPT")

    # Cleanup database connection
    await close_database()
    logger.info("Database connection closed")

    logger.info("Application shutdown complete")


def _validate_settings() -> None:
    """Validate that required settings are configured."""
    missing = []

    if not settings.SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not settings.SUPABASE_KEY:
        missing.append("SUPABASE_KEY")
    if not settings.COHERE_API_KEY:
        missing.append("COHERE_API_KEY")
    if not settings.PINECONE_API_KEY:
        missing.append("PINECONE_API_KEY")

    if missing and settings.ENVIRONMENT != "local":
        logger.warning(
            "Missing required settings",
            missing_settings=missing,
        )

    if settings.has_langfuse():
        logger.info("Langfuse observability enabled")
    else:
        logger.info("Langfuse observability not configured")
