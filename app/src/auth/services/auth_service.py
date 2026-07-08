"""Supabase-backed authentication service.

Wraps Supabase Auth (GoTrue) via a client configured with the anon/publishable
key. Sign-up triggers the DB ``handle_new_user`` function which creates the
``users`` and ``user_profiles`` rows.
"""

from typing import Any

from supabase import AsyncClient, create_async_client

from app.core.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    RegistrationError,
)
from app.core.logging import get_logger

from ..interfaces import AuthServiceABC
from ..models import AuthSession

logger = get_logger(__name__)


class SupabaseAuthService(AuthServiceABC):
    """Authentication backed by Supabase Auth."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    @classmethod
    async def create(cls, url: str, anon_key: str) -> "SupabaseAuthService":
        client = await create_async_client(url, anon_key)
        return cls(client)

    async def sign_up(
        self, email: str, password: str, full_name: str | None = None
    ) -> AuthSession:
        credentials: dict[str, Any] = {"email": email, "password": password}
        if full_name:
            credentials["options"] = {"data": {"full_name": full_name}}

        try:
            response = await self._client.auth.sign_up(credentials)  # type: ignore[arg-type]
        except Exception as e:  # noqa: BLE001 - external auth boundary.
            logger.warning("Sign-up failed", error=str(e))
            raise RegistrationError(str(e)) from e

        if not response.user or not response.session:
            # Happens when email confirmation is required (no session yet).
            raise RegistrationError(
                "Registro incompleto: puede requerir confirmación de correo."
            )

        logger.info("User signed up", user_id=response.user.id)
        return _to_session(response)

    async def sign_in(self, email: str, password: str) -> AuthSession:
        try:
            response = await self._client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
        except Exception as e:  # noqa: BLE001 - external auth boundary.
            logger.warning("Sign-in failed", error=str(e))
            raise InvalidCredentialsError() from e

        if not response.session or not response.user:
            raise InvalidCredentialsError()

        return _to_session(response)

    async def get_user_id(self, token: str) -> str:
        try:
            response = await self._client.auth.get_user(token)
        except Exception as e:  # noqa: BLE001 - external auth boundary.
            logger.warning("Token validation failed", error=str(e))
            raise AuthenticationError("Invalid or expired token") from e

        if not response or not response.user:
            raise AuthenticationError("Invalid or expired token")

        return str(response.user.id)

    async def refresh_session(self, refresh_token: str) -> AuthSession:
        try:
            response = await self._client.auth.refresh_session(refresh_token)
        except Exception as e:  # noqa: BLE001 - external auth boundary.
            logger.warning("Session refresh failed", error=str(e))
            raise AuthenticationError("Invalid or expired refresh token") from e

        if not response or not response.session or not response.user:
            raise AuthenticationError("Invalid or expired refresh token")

        return _to_session(response)


def _to_session(response: Any) -> AuthSession:
    """Map a Supabase auth response to a domain ``AuthSession``."""
    return AuthSession(
        user_id=str(response.user.id),
        email=response.user.email,
        access_token=response.session.access_token,
        refresh_token=response.session.refresh_token,
    )
