"""Health check endpoints."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("")
async def health() -> dict[str, str]:
    """Basic health check."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
    }


@router.get("/ready")
async def readiness() -> dict[str, str | bool]:
    """Readiness check - verifies all dependencies are available."""
    # TODO: Add actual dependency checks (Supabase, Pinecone, Cohere)
    return {
        "status": "ready",
        "supabase": True,
        "pinecone": True,
        "cohere": True,
    }
