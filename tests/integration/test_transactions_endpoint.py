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
        source="manual",
        created_at=datetime(2024, 12, 20, 10, 0, tzinfo=UTC),
    )


class StubService(TransactionServiceABC):
    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.created: list[TransactionCreate] = []

    async def create_transaction(
        self, transaction: TransactionCreate, user_id: str
    ) -> Transaction:
        self.created.append(transaction)
        return _sample_transaction(transaction.category or CategoryType.OTROS)

    async def get_transaction(self, transaction_id: str, user_id: str) -> Transaction:
        if not self.found:
            raise TransactionNotFoundError(transaction_id)
        return _sample_transaction()

    async def list_transactions(
        self, user_id: str, **kwargs: object
    ) -> tuple[list[Transaction], int]:
        return [_sample_transaction()], 1

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

    def test_rejects_unknown_period(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/summary", params={"period": "manana"})
        assert response.status_code == 422
