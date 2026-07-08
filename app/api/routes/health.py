"""Health check endpoints."""

from fastapi import APIRouter, Response, status

from app.core.config import settings
from app.core.logging import get_logger
from app.shared.dependencies import get_database

logger = get_logger(__name__)

router = APIRouter()


@router.get("")
async def health() -> dict[str, str]:
    """Basic liveness check (does not touch dependencies)."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
    }


@router.get("/ready")
async def readiness(response: Response) -> dict[str, str | bool]:
    """Readiness check — verifies the database is actually reachable.

    Returns 503 when a hard dependency is down so orchestrators don't route
    traffic to a pod that can't serve requests.
    """
    try:
        db_ok = await get_database().health_check()
    except Exception as e:  # noqa: BLE001 - readiness must report, not raise.
        logger.warning("Readiness DB check failed", error=str(e))
        db_ok = False

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if db_ok else "not_ready", "database": db_ok}
