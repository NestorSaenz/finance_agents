"""Unit tests for get_current_user_id (JWT resolution + demo fallback)."""

import pytest
from fastapi import HTTPException

import app.src.auth.dependencies as deps
from app.core.config import settings
from app.core.exceptions import AuthenticationError


class FakeAuthService:
    def __init__(self, user_id: str = "real-user", error: Exception | None = None) -> None:
        self.user_id = user_id
        self.error = error

    async def sign_up(self, *args: object, **kwargs: object) -> object:
        raise NotImplementedError

    async def sign_in(self, *args: object, **kwargs: object) -> object:
        raise NotImplementedError

    async def get_user_id(self, token: str) -> str:
        if self.error:
            raise self.error
        return self.user_id


class TestGetCurrentUserId:
    async def test_no_token_returns_demo_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "DEMO_USER_ID", "demo-xyz")
        result = await deps.get_current_user_id(authorization=None)
        assert result == "demo-xyz"

    async def test_no_token_no_demo_raises_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "DEMO_USER_ID", "")
        with pytest.raises(HTTPException) as exc:
            await deps.get_current_user_id(authorization=None)
        assert exc.value.status_code == 401

    async def test_demo_fallback_disabled_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Even with a demo user configured, production must require a real token.
        monkeypatch.setattr(settings, "DEMO_USER_ID", "demo-xyz")
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        with pytest.raises(HTTPException) as exc:
            await deps.get_current_user_id(authorization=None)
        assert exc.value.status_code == 401

    async def test_valid_token_returns_real_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(deps, "_auth_service", FakeAuthService(user_id="real-123"))
        result = await deps.get_current_user_id(authorization="Bearer sometoken")
        assert result == "real-123"

    async def test_invalid_token_raises_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(deps, "_auth_service", FakeAuthService(error=AuthenticationError("bad")))
        with pytest.raises(HTTPException) as exc:
            await deps.get_current_user_id(authorization="Bearer bad")
        assert exc.value.status_code == 401

    async def test_empty_bearer_raises_401(self) -> None:
        with pytest.raises(HTTPException) as exc:
            await deps.get_current_user_id(authorization="Bearer    ")
        assert exc.value.status_code == 401
