"""Integration tests for the /analysis endpoints (service overridden)."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.shared.types import UserId
from app.src.analysis.dependencies import get_analysis_service
from app.src.analysis.interfaces import AnalysisServiceABC
from app.src.analysis.models import FinancialSnapshot, MonthlyTotals, PeriodSpending
from app.src.transactions.models import CategorySpending, SpendingSummary

BASE_URL = "/api/v1/analysis"


class StubAnalysisService(AnalysisServiceABC):
    def __init__(self, surplus: Decimal = Decimal("15000")) -> None:
        self.surplus = surplus
        self.spending_calls: list[tuple[date, date]] = []
        self.spending = PeriodSpending(
            summary=SpendingSummary(
                total_income=Decimal("3000000"),
                total_expenses=Decimal("1000000"),
                by_category=[
                    CategorySpending(category="alimentacion", amount=Decimal("750000")),
                    CategorySpending(category="transporte", amount=Decimal("250000")),
                ],
                credit_expenses=Decimal("400000"),
                cash_expenses=Decimal("600000"),
            ),
            goal_saved=Decimal("500000"),
            goal_withdrawn=Decimal("80000"),
        )
        self.calls: list[tuple[str, date]] = []

    async def snapshot(
        self, user_id: UserId, period: str, today: date | None = None
    ) -> FinancialSnapshot:
        raise NotImplementedError

    async def period_spending(self, user_id, start, end):  # type: ignore[no-untyped-def]
        self.spending_calls.append((start, end))
        return self.spending

    async def monthly_trend(
        self, user_id: UserId, months: int, today: date | None = None
    ) -> list[MonthlyTotals]:
        raise NotImplementedError

    async def accumulated_surplus(self, user_id: UserId, as_of: date) -> Decimal:
        self.calls.append((user_id, as_of))
        return self.surplus


def _client(service: AnalysisServiceABC) -> Iterator[TestClient]:
    app.dependency_overrides[get_analysis_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def stub() -> StubAnalysisService:
    return StubAnalysisService()


@pytest.fixture
def client(stub: StubAnalysisService) -> Iterator[TestClient]:
    yield from _client(stub)


class TestAccumulatedSurplus:
    def test_returns_surplus_serialized_as_string(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/excedente", params={"period": "este_mes"})

        assert response.status_code == 200
        assert response.json() == {"accumulated_surplus": "15000"}

    def test_defaults_to_este_mes(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/excedente")

        assert response.status_code == 200

    def test_resolves_month_end_for_a_specific_month(
        self, stub: StubAnalysisService
    ) -> None:
        gen = _client(stub)
        client = next(gen)
        try:
            response = client.get(f"{BASE_URL}/excedente", params={"period": "2026-06"})
            assert response.status_code == 200
            # The route resolves the period to its month-end before delegating.
            assert stub.calls[0][1] == date(2026, 6, 30)
        finally:
            next(gen, None)

    def test_supports_negative_surplus(self) -> None:
        gen = _client(StubAnalysisService(surplus=Decimal("-2500")))
        client = next(gen)
        try:
            response = client.get(f"{BASE_URL}/excedente")
            assert response.status_code == 200
            assert response.json()["accumulated_surplus"] == "-2500"
        finally:
            next(gen, None)


class TestPeriodSpendingSummary:
    def test_shape_and_meaning_of_every_field(self, client: TestClient, stub: StubAnalysisService) -> None:
        response = client.get(f"{BASE_URL}/summary", params={"period": "2026-11"})

        assert response.status_code == 200
        body = response.json()
        assert stub.spending_calls == [(date(2026, 11, 1), date(2026, 11, 30))]
        assert body["period"] == "2026-11"
        assert body["total_income"] == "3000000"
        assert body["total_expenses"] == "1000000"  # CONSUMPTION only, like /transactions/summary
        assert body["goal_saved"] == "500000"
        assert body["goal_withdrawn"] == "80000"
        assert body["total_spent"] == "1500000"  # consumption + goal_saved
        assert body["balance"] == "1500000"  # income - total_spent: goals ALREADY included
        assert body["goal_spending_from"] == settings.GOALS_COUNT_AS_SPENDING_FROM.isoformat()

    def test_credit_plus_cash_equals_the_consumption_total(self, client: TestClient) -> None:
        body = client.get(f"{BASE_URL}/summary").json()

        assert Decimal(body["credit_expenses"]) + Decimal(body["cash_expenses"]) == Decimal(
            body["total_expenses"]
        )

    def test_category_shares_are_over_the_consumption(self, client: TestClient) -> None:
        body = client.get(f"{BASE_URL}/summary").json()

        assert [(c["category"], c["percentage"]) for c in body["by_category"]] == [
            ("alimentacion", 75.0),
            ("transporte", 25.0),
        ]

    def test_defaults_to_este_mes_and_accepts_named_periods(self, client: TestClient) -> None:
        assert client.get(f"{BASE_URL}/summary").json()["period"] == "este_mes"
        for period in ("mes_pasado", "todo", "2026-02"):
            assert client.get(f"{BASE_URL}/summary", params={"period": period}).status_code == 200

    def test_invalid_period_is_a_422(self, client: TestClient) -> None:
        assert client.get(f"{BASE_URL}/summary", params={"period": "2026-13"}).status_code == 422
        assert client.get(f"{BASE_URL}/summary", params={"period": "manana"}).status_code == 422

    def test_a_summary_without_goal_savings_has_the_old_balance(self, stub: StubAnalysisService) -> None:
        stub.spending = PeriodSpending(summary=stub.spending.summary)
        for client in _client(stub):
            body = client.get(f"{BASE_URL}/summary").json()

        assert body["total_spent"] == body["total_expenses"]
        assert body["balance"] == "2000000"  # 3.000.000 - 1.000.000
