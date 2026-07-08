"""Data Transfer Objects for the auth API layer."""

from pydantic import BaseModel, Field

from .constants import MIN_PASSWORD_LENGTH
from .models import AuthSession


class SignupRequest(BaseModel):
    """Request body for user registration."""

    email: str = Field(..., min_length=3, examples=["nes164@gmail.com"])
    password: str = Field(..., min_length=MIN_PASSWORD_LENGTH, examples=["secret123"])
    full_name: str | None = Field(default=None, examples=["Néstor Sáenz"])


class LoginRequest(BaseModel):
    """Request body for user login."""

    email: str = Field(..., min_length=3, examples=["nes164@gmail.com"])
    password: str = Field(..., examples=["secret123"])


class RefreshRequest(BaseModel):
    """Request body to exchange a refresh token for a fresh session."""

    refresh_token: str = Field(..., min_length=1)


class SessionResponse(BaseModel):
    """Response body with the authenticated session tokens."""

    access_token: str = Field(..., description="JWT to send as 'Authorization: Bearer <token>'")
    refresh_token: str
    user_id: str
    email: str | None

    @classmethod
    def from_domain(cls, session: AuthSession) -> "SessionResponse":
        return cls(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            user_id=session.user_id,
            email=session.email,
        )
