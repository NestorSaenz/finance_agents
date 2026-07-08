"""Dependency injection and the current-user resolver for the auth module."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.logging import get_logger

from .constants import BEARER_PREFIX
from .interfaces import AuthServiceABC
from .services.auth_service import SupabaseAuthService

logger = get_logger(__name__)

# Global auth service instance (initialized in the app lifespan).
_auth_service: SupabaseAuthService | None = None


async def init_auth() -> None:
    """Initialize the auth service (called during app startup)."""
    global _auth_service
    if settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY:
        _auth_service = await SupabaseAuthService.create(
            settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY
        )
        logger.info("Auth service initialized")


async def close_auth() -> None:
    """Tear down the auth service (called during app shutdown)."""
    global _auth_service
    _auth_service = None


def get_auth_service() -> AuthServiceABC:
    """Return the auth service or raise if not initialized."""
    if _auth_service is None:
        raise RuntimeError(
            "Auth service not initialized. Set SUPABASE_ANON_KEY and run init_auth()."
        )
    return _auth_service


AuthServiceDep = Annotated[AuthServiceABC, Depends(get_auth_service)]


async def get_current_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Resolve the current user id.

    With an ``Authorization: Bearer <jwt>`` header, validates the token via
    Supabase and returns the real user id. Without a token, falls back to
    ``settings.DEMO_USER_ID`` ONLY outside production, so a real deployment always
    requires authentication while local/demo stays convenient.

    Raises:
        HTTPException: 401 if a token is present but invalid, or if no valid token
            is supplied and the demo fallback is not allowed.
    """
    if not authorization:
        # Demo fallback is a convenience for local/staging; never in production.
        if settings.DEMO_USER_ID and not settings.is_production():
            return settings.DEMO_USER_ID
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header"
        )

    token = authorization.removeprefix(BEARER_PREFIX).strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty bearer token"
        )

    try:
        return await get_auth_service().get_user_id(token)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message
        ) from e


CurrentUserId = Annotated[str, Depends(get_current_user_id)]
