"""Integration tests for the /transactions endpoints (service overridden)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import TransactionNotFoundError
from app.main import app
from app.shared.types import CategoryType, CurrencyType, TransactionType
from app.src.transactions.dependencies import get_transaction_service
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import (
    CategorySpending,
    SpendingSummary,
    Transaction,
    TransactionCreate,
)

BASE_URL = "/api/v1/transactions"


def _sample_transaction(category: CategoryType = CategoryType.RESTAURANTES) -> Transaction:
    return Transaction(
        id="tx-1",
        user_id="demo-user",
        amount=Decimal("50000"),
        currency=CurrencyType.MXN,
        transaction_type=TransactionType.EXPENSE,
        description="Almuerzo con colegas",
        category=category,
        transaction_date=date(2024, 12, 20),
        budget_date=date(2024, 12, 20),
        source="manual",
        created_at=datetime(2024, 12, 20, 10, 0, tzinfo=UTC),
    )


class StubService(TransactionServiceABC):
    def __init__(
        self, found: bool = True, movements: list[Transaction] | None = None
    ) -> None:
        self.found = found
        self.movements = movements
        self.created: list[TransactionCreate] = []

    async def create_transaction(
        self, transaction: TransactionCreate, user_id: str
    ) -> Transaction:
        self.created.append(transaction)
        return _sample_transaction(transaction.category or CategoryType.OTROS)

    async def create_installments(
        self, base: TransactionCreate, installments: int, user_id: str
    ) -> list[Transaction]:
        return [
            await self.create_transaction(base, user_id) for _ in range(installments)
        ]

    async def get_transaction(self, transaction_id: str, user_id: str) -> Transaction:
        if not self.found:
            raise TransactionNotFoundError(transaction_id)
        return _sample_transaction()

    async def list_transactions(
        self, user_id: str, **kwargs: object
    ) -> tuple[list[Transaction], int]:
        return [_sample_transaction()], 1

    async def list_by_period(
        self, user_id: str, **kwargs: object
    ) -> list[Transaction]:
        return self.movements if self.movements is not None else [_sample_transaction()]

    async def delete_by_card_and_period(self, user_id: str, card_id: str, **kwargs: object) -> int:
        return 0

    async def resolve_category(self, proposed: str, user_id: str) -> str:
        return proposed

    async def count_by_category(self, user_id: str, category: str) -> int:
        return 0

    async def list_categories(self, user_id: str) -> list[str]:
        return []

    async def recategorize(self, user_id: str, old: str, new: str) -> int:
        return 0

    async def delete_by_category(self, user_id: str, category: str) -> int:
        return 0

    async def update_transaction(
        self, transaction_id: str, user_id: str, **kwargs: object
    ) -> Transaction:
        return _sample_transaction()

    async def delete_transaction(self, transaction_id: str, user_id: str) -> Transaction:
        return _sample_transaction()

    async def get_spending_summary(
        self, user_id: str, **kwargs: object
    ) -> SpendingSummary:
        return SpendingSummary(
            total_income=Decimal("100000"),
            total_expenses=Decimal("50000"),
            by_category=[
                CategorySpending(
                    category=CategoryType.RESTAURANTES, amount=Decimal("50000")
                )
            ],
        )


def _client_with_service(service: TransactionServiceABC) -> Iterator[TestClient]:
    app.dependency_overrides[get_transaction_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from _client_with_service(StubService())


class TestCreateTransaction:
    def test_creates_with_explicit_category(self, client: TestClient) -> None:
        response = client.post(
            BASE_URL,
            json={
                "amount": 50000,
                "description": "Almuerzo con colegas",
                "transaction_type": "expense",
                "category": "restaurantes",
                "transaction_date": "2024-12-20",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == "tx-1"
        assert body["category"] == "restaurantes"

    def test_rejects_negative_amount(self, client: TestClient) -> None:
        response = client.post(
            BASE_URL,
            json={
                "amount": -10,
                "description": "x",
                "transaction_type": "expense",
                "transaction_date": "2024-12-20",
            },
        )
        assert response.status_code == 422


class TestListTransactions:
    def test_returns_paginated_list(self, client: TestClient) -> None:
        response = client.get(BASE_URL, params={"page": 1, "page_size": 20})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["transactions"]) == 1
        assert body["page"] == 1

    def test_period_returns_the_full_movement_list(self, client: TestClient) -> None:
        # With a period the endpoint returns every movement in range (no paging).
        response = client.get(BASE_URL, params={"period": "este_mes"})
        assert response.status_code == 200
        body = response.json()
        assert len(body["transactions"]) == body["total"] == 1
        assert body["transactions"][0]["description"]

    def test_period_with_no_movements_returns_empty_ok(self) -> None:
        # An empty period must be 200 with page_size=0, not a 500 from the DTO.
        gen = _client_with_service(StubService(movements=[]))
        client = next(gen)
        try:
            response = client.get(BASE_URL, params={"period": "2020-01"})
            assert response.status_code == 200
            body = response.json()
            assert body["transactions"] == []
            assert body["total"] == 0
            assert body["page_size"] == 0
        finally:
            gen.close()

    def test_period_with_over_100_movements_is_not_capped_by_the_dto(self) -> None:
        # A full list larger than the request page window (100) must still serialize.
        many = [_sample_transaction() for _ in range(150)]
        gen = _client_with_service(StubService(movements=many))
        client = next(gen)
        try:
            response = client.get(BASE_URL, params={"period": "todo"})
            assert response.status_code == 200
            body = response.json()
            assert body["total"] == 150
            assert len(body["transactions"]) == 150
        finally:
            gen.close()


class TestGetTransaction:
    def test_returns_transaction(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/tx-1")
        assert response.status_code == 200
        assert response.json()["id"] == "tx-1"

    def test_missing_transaction_returns_404(self) -> None:
        gen = _client_with_service(StubService(found=False))
        client = next(gen)
        try:
            response = client.get(f"{BASE_URL}/does-not-exist")
            assert response.status_code == 404
            assert response.json()["error"] == "TRANSACTION_NOT_FOUND"
        finally:
            next(gen, None)


class TestSpendingSummary:
    def test_returns_summary_with_percentages(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/summary", params={"period": "este_mes"})
        assert response.status_code == 200
        body = response.json()
        assert body["period"] == "este_mes"
        assert body["total_income"] == "100000"
        assert body["total_expenses"] == "50000"
        assert body["balance"] == "50000"
        assert body["by_category"][0]["category"] == "restaurantes"
        assert body["by_category"][0]["percentage"] == 100.0
        # Credit vs cash split is present (defaults to 0 in the stub).
        assert body["credit_expenses"] == "0"
        assert body["cash_expenses"] == "0"

    def test_accepts_a_specific_month(self, client: TestClient) -> None:
        # A month is passed as YYYY-MM so the dashboard can view any past month.
        response = client.get(f"{BASE_URL}/summary", params={"period": "2026-02"})
        assert response.status_code == 200
        assert response.json()["period"] == "2026-02"

    def test_unknown_period_falls_back_gracefully(self, client: TestClient) -> None:
        # Period is now free-form (to allow YYYY-MM); an unrecognized value is
        # resolved leniently to the current month instead of rejected.
        response = client.get(f"{BASE_URL}/summary", params={"period": "manana"})
        assert response.status_code == 200
