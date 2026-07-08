"""Contracts (ABCs) for the auth module."""

from abc import ABC, abstractmethod

from .models import AuthSession


class AuthServiceABC(ABC):
    """Contract for user authentication (backed by Supabase Auth)."""

    @abstractmethod
    async def sign_up(
        self, email: str, password: str, full_name: str | None = None
    ) -> AuthSession:
        """Register a new user and return their session.

        Raises ``RegistrationError`` on failure (email taken, weak password...).
        """

    @abstractmethod
    async def sign_in(self, email: str, password: str) -> AuthSession:
        """Authenticate a user and return their session.

        Raises ``InvalidCredentialsError`` on wrong credentials.
        """

    @abstractmethod
    async def get_user_id(self, token: str) -> str:
        """Validate a JWT access token and return the user id (``sub``).

        Raises ``AuthenticationError`` if the token is invalid or expired.
        """

    @abstractmethod
    async def refresh_session(self, refresh_token: str) -> AuthSession:
        """Exchange a refresh token for a fresh session (new access token).

        Raises ``AuthenticationError`` if the refresh token is invalid/expired.
        """
