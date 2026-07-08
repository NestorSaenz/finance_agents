"""Unit tests for the Supabase auth service (Supabase client mocked)."""

from types import SimpleNamespace

import pytest

from app.core.exceptions import (
    AuthenticationError,
    InvalidCredentialsError,
    RegistrationError,
)
from app.src.auth.services.auth_service import SupabaseAuthService


def _auth_response(user_id: str = "u1", email: str = "a@b.com", token: str = "jwt-abc") -> object:
    return SimpleNamespace(
        user=SimpleNamespace(id=user_id, email=email),
        session=SimpleNamespace(access_token=token, refresh_token="refresh-xyz"),
    )


class FakeAuth:
    def __init__(self) -> None:
        self.signup_response: object = _auth_response()
        self.signin_response: object = _auth_response()
        self.user_response: object = SimpleNamespace(user=SimpleNamespace(id="u1", email="a@b.com"))
        self.error: Exception | None = None

    async def sign_up(self, credentials: dict) -> object:
        if self.error:
            raise self.error
        return self.signup_response

    async def sign_in_with_password(self, credentials: dict) -> object:
        if self.error:
            raise self.error
        return self.signin_response

    async def get_user(self, token: str) -> object:
        if self.error:
            raise self.error
        return self.user_response


def _service(auth: FakeAuth) -> SupabaseAuthService:
    return SupabaseAuthService(SimpleNamespace(auth=auth))  # type: ignore[arg-type]


class TestSignUp:
    async def test_returns_session(self) -> None:
        service = _service(FakeAuth())
        session = await service.sign_up("a@b.com", "secret123", full_name="Nestor")
        assert session.user_id == "u1"
        assert session.access_token == "jwt-abc"
        assert session.email == "a@b.com"

    async def test_provider_error_raises_registration_error(self) -> None:
        auth = FakeAuth()
        auth.error = RuntimeError("email already registered")
        with pytest.raises(RegistrationError):
            await _service(auth).sign_up("a@b.com", "secret123")

    async def test_no_session_raises_registration_error(self) -> None:
        auth = FakeAuth()
        auth.signup_response = SimpleNamespace(user=SimpleNamespace(id="u1", email="a@b.com"), session=None)
        with pytest.raises(RegistrationError):
            await _service(auth).sign_up("a@b.com", "secret123")


class TestSignIn:
    async def test_returns_session(self) -> None:
        session = await _service(FakeAuth()).sign_in("a@b.com", "secret123")
        assert session.user_id == "u1"
        assert session.access_token == "jwt-abc"

    async def test_wrong_credentials_raise(self) -> None:
        auth = FakeAuth()
        auth.error = RuntimeError("invalid login")
        with pytest.raises(InvalidCredentialsError):
            await _service(auth).sign_in("a@b.com", "bad")


class TestGetUserId:
    async def test_valid_token_returns_user_id(self) -> None:
        assert await _service(FakeAuth()).get_user_id("jwt-abc") == "u1"

    async def test_invalid_token_raises_authentication_error(self) -> None:
        auth = FakeAuth()
        auth.error = RuntimeError("invalid token")
        with pytest.raises(AuthenticationError):
            await _service(auth).get_user_id("bad")

    async def test_no_user_raises_authentication_error(self) -> None:
        auth = FakeAuth()
        auth.user_response = SimpleNamespace(user=None)
        with pytest.raises(AuthenticationError):
            await _service(auth).get_user_id("jwt")
