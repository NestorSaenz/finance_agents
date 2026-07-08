"""Integration tests for the /auth endpoints (auth service overridden)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import InvalidCredentialsError, RegistrationError
from app.main import app
from app.src.auth.dependencies import get_auth_service
from app.src.auth.interfaces import AuthServiceABC
from app.src.auth.models import AuthSession

SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"


class StubAuthService(AuthServiceABC):
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def sign_up(self, email: str, password: str, full_name: str | None = None) -> AuthSession:
        if self.error:
            raise self.error
        return AuthSession(user_id="u1", email=email, access_token="jwt-abc", refresh_token="r")

    async def sign_in(self, email: str, password: str) -> AuthSession:
        if self.error:
            raise self.error
        return AuthSession(user_id="u1", email=email, access_token="jwt-abc", refresh_token="r")

    async def get_user_id(self, token: str) -> str:
        return "u1"

    async def refresh_session(self, refresh_token: str) -> AuthSession:
        if self.error:
            raise self.error
        return AuthSession(
            user_id="u1", email="a@b.com", access_token="jwt-new", refresh_token="r2"
        )


def _client(service: AuthServiceABC) -> Iterator[TestClient]:
    app.dependency_overrides[get_auth_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from _client(StubAuthService())


class TestSignup:
    def test_returns_tokens(self, client: TestClient) -> None:
        response = client.post(SIGNUP_URL, json={"email": "a@b.com", "password": "secret123"})
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "jwt-abc"
        assert body["user_id"] == "u1"

    def test_short_password_rejected(self, client: TestClient) -> None:
        response = client.post(SIGNUP_URL, json={"email": "a@b.com", "password": "x"})
        assert response.status_code == 422

    def test_registration_failure_returns_400(self) -> None:
        gen = _client(StubAuthService(error=RegistrationError("email already registered")))
        c = next(gen)
        try:
            response = c.post(SIGNUP_URL, json={"email": "a@b.com", "password": "secret123"})
            assert response.status_code == 400
        finally:
            next(gen, None)


class TestLogin:
    def test_returns_tokens(self, client: TestClient) -> None:
        response = client.post(LOGIN_URL, json={"email": "a@b.com", "password": "secret123"})
        assert response.status_code == 200
        assert response.json()["access_token"] == "jwt-abc"

    def test_bad_credentials_returns_401(self) -> None:
        gen = _client(StubAuthService(error=InvalidCredentialsError()))
        c = next(gen)
        try:
            response = c.post(LOGIN_URL, json={"email": "a@b.com", "password": "bad"})
            assert response.status_code == 401
        finally:
            next(gen, None)


class TestRefresh:
    def test_returns_fresh_tokens(self, client: TestClient) -> None:
        response = client.post(REFRESH_URL, json={"refresh_token": "r"})
        assert response.status_code == 200
        assert response.json()["access_token"] == "jwt-new"

    def test_invalid_refresh_returns_401(self) -> None:
        from app.core.exceptions import AuthenticationError

        gen = _client(StubAuthService(error=AuthenticationError("expired")))
        c = next(gen)
        try:
            response = c.post(REFRESH_URL, json={"refresh_token": "bad"})
            assert response.status_code == 401
        finally:
            next(gen, None)
