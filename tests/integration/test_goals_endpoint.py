"""Integration tests for the /goals endpoints (service overridden)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import GoalNotFoundError
from app.main import app
from app.shared.types import CurrencyType, GoalId, GoalStatus, GoalType, UserId
from app.src.goals.dependencies import get_goal_service
from app.src.goals.interfaces import GoalServiceABC
from app.src.goals.models import Goal, GoalContribution, GoalCreate, GoalProgress

BASE_URL = "/api/v1/goals"


def _goal(status: GoalStatus = GoalStatus.ACTIVE) -> Goal:
    return Goal(
        id="goal-1",
        user_id="demo-user",
        name="Viaje a Japón",
        description=None,
        goal_type=GoalType.SAVINGS,
        target_amount=Decimal("100000"),
        current_amount=Decimal("30000"),
        currency=CurrencyType.MXN,
        target_date=date(2025, 12, 31),
        monthly_contribution=None,
        status=status,
        priority=1,
        created_at=datetime(2024, 12, 1, tzinfo=UTC),
    )


class StubGoalService(GoalServiceABC):
    def __init__(self, found: bool = True) -> None:
        self.found = found

    async def create_goal(self, goal: GoalCreate, user_id: UserId) -> Goal:
        return _goal()

    async def get_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        return _goal()

    async def list_goals(
        self,
        user_id: UserId,
        *,
        page: int,
        page_size: int,
        as_of: date | None = None,
    ) -> tuple[list[Goal], int]:
        return [_goal()], 1

    async def contribute(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date | None = None,
    ) -> Goal:
        return _goal(status=GoalStatus.COMPLETED)

    async def contributed_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> Decimal:
        return Decimal("1500")

    async def update_goal(
        self,
        goal_id: GoalId,
        user_id: UserId,
        *,
        name: str | None = None,
        target_amount: Decimal | None = None,
        target_date: date | None = None,
    ) -> Goal:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        return _goal()

    async def delete_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        return _goal()

    async def list_contributions(
        self, goal_id: GoalId, user_id: UserId
    ) -> list[GoalContribution]:
        return []

    async def remove_contribution(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date | None = None,
    ) -> Goal | None:
        if not self.found:
            return None
        return _goal()

    async def get_progress(
        self, goal_id: GoalId, user_id: UserId, as_of: date | None = None
    ) -> GoalProgress:
        return GoalProgress(
            goal=_goal(),
            percentage=30.0,
            remaining=Decimal("70000"),
            is_completed=False,
            months_remaining=11,
            required_monthly_contribution=Decimal("6363.64"),
            on_track=True,
        )


def _client(service: GoalServiceABC) -> Iterator[TestClient]:
    app.dependency_overrides[get_goal_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from _client(StubGoalService())


class TestCrud:
    def test_create_goal(self, client: TestClient) -> None:
        response = client.post(
            BASE_URL,
            json={"name": "Viaje a Japón", "target_amount": 100000, "current_amount": 30000},
        )
        assert response.status_code == 200
        assert response.json()["id"] == "goal-1"

    def test_list_goals(self, client: TestClient) -> None:
        response = client.get(BASE_URL)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["total_contributed"] == "0"  # no period → not computed

    def test_list_goals_reports_contributed_for_period(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}?period=2026-06")
        assert response.status_code == 200
        assert response.json()["total_contributed"] == "1500"

    def test_missing_goal_returns_404(self) -> None:
        gen = _client(StubGoalService(found=False))
        client = next(gen)
        try:
            response = client.get(f"{BASE_URL}/nope")
            assert response.status_code == 404
            assert response.json()["error"] == "GOAL_NOT_FOUND"
        finally:
            next(gen, None)

    def test_delete_goal(self, client: TestClient) -> None:
        response = client.delete(f"{BASE_URL}/goal-1")
        assert response.status_code == 200
        assert response.json()["id"] == "goal-1"

    def test_delete_missing_goal_returns_404(self) -> None:
        gen = _client(StubGoalService(found=False))
        client = next(gen)
        try:
            response = client.delete(f"{BASE_URL}/nope")
            assert response.status_code == 404
        finally:
            next(gen, None)


class TestProgressAndContribute:
    def test_progress(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/goal-1/progress")
        assert response.status_code == 200
        body = response.json()
        assert body["percentage"] == 30.0
        assert body["required_monthly_contribution"] == "6363.64"

    def test_contribute(self, client: TestClient) -> None:
        response = client.post(f"{BASE_URL}/goal-1/contribute", json={"amount": 5000})
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
