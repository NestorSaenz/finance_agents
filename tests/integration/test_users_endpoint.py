"""Integration tests for the /users profile & onboarding endpoints."""

from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.types import UserId
from app.src.users.dependencies import get_user_profile_service
from app.src.users.interfaces import UserProfileServiceABC
from app.src.users.models import UserProfile, UserProfileUpdate

BASE_URL = "/api/v1/users"


class StubProfileService(UserProfileServiceABC):
    def __init__(self, completed: bool = False) -> None:
        self.completed = completed
        self.updates: list[tuple[str, UserProfileUpdate]] = []

    async def get_profile(self, user_id: UserId) -> UserProfile:
        return UserProfile(
            user_id=user_id,
            monthly_income=Decimal("30000") if self.completed else None,
            onboarding_completed=self.completed,
        )

    async def update_profile(
        self, user_id: UserId, data: UserProfileUpdate
    ) -> UserProfile:
        self.updates.append((user_id, data))
        return UserProfile(
            user_id=user_id,
            monthly_income=data.monthly_income,
            savings_goal_percentage=data.savings_goal_percentage,
            onboarding_completed=bool(data.onboarding_completed),
        )


def _client(service: UserProfileServiceABC) -> Iterator[TestClient]:
    app.dependency_overrides[get_user_profile_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def service() -> StubProfileService:
    return StubProfileService()


class TestGetProfile:
    def test_returns_not_onboarded_by_default(self) -> None:
        gen = _client(StubProfileService(completed=False))
        client = next(gen)
        try:
            response = client.get(f"{BASE_URL}/me/profile")
            assert response.status_code == 200
            body = response.json()
            assert body["onboarding_completed"] is False
            assert body["monthly_income"] is None
        finally:
            next(gen, None)


class TestOnboarding:
    def test_completes_with_income_and_savings_goal(
        self, service: StubProfileService
    ) -> None:
        gen = _client(service)
        client = next(gen)
        try:
            response = client.post(
                f"{BASE_URL}/me/onboarding",
                json={"monthly_income": 30000, "savings_goal_percentage": 20},
            )
            assert response.status_code == 200
            body = response.json()
            assert body["onboarding_completed"] is True
            assert body["monthly_income"] == "30000"
            assert body["savings_goal_percentage"] == "20"
            # It should flag onboarding as completed regardless of the payload.
            assert service.updates[0][1].onboarding_completed is True
        finally:
            next(gen, None)

    def test_rejects_savings_goal_over_100(self, service: StubProfileService) -> None:
        gen = _client(service)
        client = next(gen)
        try:
            response = client.post(
                f"{BASE_URL}/me/onboarding", json={"savings_goal_percentage": 150}
            )
            assert response.status_code == 422
        finally:
            next(gen, None)

    def test_completes_when_skipped(self, service: StubProfileService) -> None:
        gen = _client(service)
        client = next(gen)
        try:
            response = client.post(f"{BASE_URL}/me/onboarding", json={})
            assert response.status_code == 200
            body = response.json()
            assert body["onboarding_completed"] is True
            assert body["monthly_income"] is None
        finally:
            next(gen, None)

    def test_rejects_negative_income(self, service: StubProfileService) -> None:
        gen = _client(service)
        client = next(gen)
        try:
            response = client.post(
                f"{BASE_URL}/me/onboarding", json={"monthly_income": -5}
            )
            assert response.status_code == 422
        finally:
            next(gen, None)
