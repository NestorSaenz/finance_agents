"""Domain models for the auth module."""

from pydantic import BaseModel


class AuthSession(BaseModel):
    """An authenticated session returned by sign-up / sign-in."""

    user_id: str
    email: str | None
    access_token: str
    refresh_token: str
