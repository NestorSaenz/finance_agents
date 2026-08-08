"""Integration tests for the /budgets endpoints (service overridden)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import BudgetNotFoundError
from app.main import app
from app.shared.types import BudgetId, BudgetPeriod, CategoryType, CurrencyType, UserId
from app.src.budgets.dependencies import get_budget_service
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.budgets.models import Budget, BudgetCreate, BudgetStatus

BASE_URL = "/api/v1/budgets"


def _budget() -> Budget:
    return Budget(
        id="bud-1",
        user_id="demo-user",
        name="Comida mensual",
        amount=Decimal("300000"),
        category=CategoryType.RESTAURANTES,
        currency=CurrencyType.MXN,
        period_type=BudgetPeriod.MONTHLY,
        start_date=date(2024, 12, 1),
        end_date=None,
        alert_threshold=Decimal("80"),
        alert_enabled=True,
        is_active=True,
        created_at=datetime(2024, 12, 1, tzinfo=UTC),
    )


def _status(alert: bool) -> BudgetStatus:
    return BudgetStatus(
        budget=_budget(),
        period_start=date(2024, 12, 1),
        period_end=date(2024, 12, 31),
        spent=Decimal("250000"),
        remaining=Decimal("50000"),
        percentage=83.33,
        alert_triggered=alert,
    )


class StubBudgetService(BudgetServiceABC):
    def __init__(self, found: bool = True, alerting: bool = True) -> None:
        self.found = found
        self.alerting = alerting

    async def create_budget(self, budget: BudgetCreate, user_id: UserId) -> Budget:
        return _budget()

    async def get_budget(self, budget_id: BudgetId, user_id: UserId) -> Budget:
        if not self.found:
            raise BudgetNotFoundError(budget_id)
        return _budget()

    async def list_budgets(
        self, user_id: UserId, *, page: int, page_size: int
    ) -> tuple[list[Budget], int]:
        return [_budget()], 1

    async def get_budget_status(
        self, budget_id: BudgetId, user_id: UserId, as_of: date | None = None
    ) -> BudgetStatus:
        if not self.found:
            raise BudgetNotFoundError(budget_id)
        return _status(self.alerting)

    async def get_active_alerts(
        self, user_id: UserId, as_of: date | None = None
    ) -> list[BudgetStatus]:
        return [_status(True)] if self.alerting else []

    async def get_all_status(
        self, user_id: UserId, as_of: date | None = None
    ) -> list[BudgetStatus]:
        return [_status(self.alerting)]

    async def update_budget(
        self,
        budget_id: BudgetId,
        user_id: UserId,
        *,
        name: str | None = None,
        amount: Decimal | None = None,
    ) -> Budget:
        if not self.found:
            raise BudgetNotFoundError(budget_id)
        return _budget()

    async def delete_budget(self, budget_id: BudgetId, user_id: UserId) -> Budget:
        if not self.found:
            raise BudgetNotFoundError(budget_id)
        return _budget()

    async def resolve_budget(self, reference: str, user_id: UserId) -> Budget | None:
        return _budget() if self.found else None

    async def recategorize(self, user_id: UserId, old: str, new: str) -> int:
        return 0

    async def delete_by_category(self, user_id: UserId, category: str) -> int:
        return 0


def _client(service: BudgetServiceABC) -> Iterator[TestClient]:
    app.dependency_overrides[get_budget_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from _client(StubBudgetService())


class TestCreateAndList:
    def test_create_budget(self, client: TestClient) -> None:
        response = client.post(
            BASE_URL,
            json={
                "name": "Comida mensual",
                "amount": 300000,
                "category": "restaurantes",
                "period_type": "monthly",
                "start_date": "2024-12-01",
            },
        )
        assert response.status_code == 200
        assert response.json()["id"] == "bud-1"

    def test_list_budgets(self, client: TestClient) -> None:
        response = client.get(BASE_URL)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["budgets"]) == 1


class TestStatusAndAlerts:
    def test_status_returns_spending(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/bud-1/status")
        assert response.status_code == 200
        body = response.json()
        assert body["spent"] == "250000"
        assert body["alert_triggered"] is True

    def test_alerts_endpoint(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/alerts")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["alerts"][0]["alert_triggered"] is True

    def test_all_status_endpoint(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/status")
        assert response.status_code == 200
        body = response.json()
        assert len(body["statuses"]) == 1
        assert body["total_budgeted"] == "300000"
        assert body["total_spent"] == "250000"

    def test_missing_budget_returns_404(self) -> None:
        gen = _client(StubBudgetService(found=False))
        client = next(gen)
        try:
            response = client.get(f"{BASE_URL}/nope")
            assert response.status_code == 404
            assert response.json()["error"] == "BUDGET_NOT_FOUND"
        finally:
            next(gen, None)
