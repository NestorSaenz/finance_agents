"""Integration tests for the /analysis endpoints (service overridden)."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.shared.types import UserId
from app.src.analysis.dependencies import get_analysis_service
from app.src.analysis.interfaces import AnalysisServiceABC
from app.src.analysis.models import FinancialSnapshot

BASE_URL = "/api/v1/analysis"


class StubAnalysisService(AnalysisServiceABC):
    def __init__(self, surplus: Decimal = Decimal("15000")) -> None:
        self.surplus = surplus
        self.calls: list[tuple[str, date]] = []

    async def snapshot(self, user_id: UserId, period: str) -> FinancialSnapshot:
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
