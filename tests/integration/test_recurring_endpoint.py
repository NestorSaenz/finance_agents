"""Integration tests for the /recurring endpoints (service overridden)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.shared.types import TransactionType, UserId
from app.src.recurring.dependencies import get_recurring_service
from app.src.recurring.interfaces import RecurringServiceABC
from app.src.recurring.models import (
    RecurringCreate,
    RecurringFrequency,
    RecurringTransaction,
    RecurringUpdate,
)

BASE_URL = "/api/v1/recurring"
SECRET = "top-secret-run-token"


def _rec() -> RecurringTransaction:
    return RecurringTransaction(
        id="rec-1",
        user_id="demo-user",
        amount=Decimal("50000"),
        description="Netflix",
        transaction_type=TransactionType.EXPENSE,
        category="suscripciones",
        payment_method=None,
        card_id=None,
        frequency=RecurringFrequency.MONTHLY,
        day_of_month=5,
        next_run_date=date(2026, 6, 5),
        last_run_date=None,
        active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class StubRecurringService(RecurringServiceABC):
    def __init__(self, run_created: int = 3) -> None:
        self.run_created = run_created
        self.run_calls = 0

    async def create_recurring(
        self, rec: RecurringCreate, user_id: UserId
    ) -> RecurringTransaction:
        return _rec()

    async def list_recurring(self, user_id: UserId) -> list[RecurringTransaction]:
        return [_rec()]

    async def update_recurring(
        self, recurring_id: str, user_id: UserId, data: RecurringUpdate
    ) -> RecurringTransaction:
        return _rec()

    async def delete_recurring(
        self, recurring_id: str, user_id: UserId
    ) -> RecurringTransaction:
        return _rec()

    async def set_active(
        self, recurring_id: str, user_id: UserId, active: bool
    ) -> RecurringTransaction:
        return _rec()

    async def resolve_by_name(
        self, name: str, user_id: UserId
    ) -> RecurringTransaction | None:
        return _rec()

    async def find_matches(
        self, name: str, user_id: UserId
    ) -> list[RecurringTransaction]:
        return [_rec()]

    async def run_due(self, now: datetime) -> int:
        self.run_calls += 1
        return self.run_created


def _client(service: RecurringServiceABC) -> Iterator[TestClient]:
    app.dependency_overrides[get_recurring_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from _client(StubRecurringService())


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RECURRING_RUN_SECRET", SECRET)


class TestList:
    def test_list_returns_user_rows(self, client: TestClient) -> None:
        response = client.get(BASE_URL)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["recurring"][0]["description"] == "Netflix"
        assert body["recurring"][0]["amount"] == "50000"  # Decimal -> string
        assert body["recurring"][0]["active"] is True


class TestCreate:
    def test_create_valid_returns_row(self, client: TestClient) -> None:
        response = client.post(
            BASE_URL,
            json={
                "amount": "50000",
                "description": "Netflix",
                "transaction_type": "expense",
                "day_of_month": 5,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["description"] == "Netflix"
        assert body["amount"] == "50000"  # Decimal -> string
        assert body["day_of_month"] == 5

    def test_create_invalid_day_rejected(self, client: TestClient) -> None:
        response = client.post(
            BASE_URL,
            json={
                "amount": "50000",
                "description": "Netflix",
                "transaction_type": "expense",
                "day_of_month": 32,
            },
        )
        assert response.status_code == 422

    def test_create_invalid_amount_rejected(self, client: TestClient) -> None:
        response = client.post(
            BASE_URL,
            json={
                "amount": "0",
                "description": "Netflix",
                "transaction_type": "expense",
                "day_of_month": 5,
            },
        )
        assert response.status_code == 422


class TestRun:
    def test_run_with_correct_secret_runs(self, client: TestClient) -> None:
        response = client.post(
            f"{BASE_URL}/run", headers={"X-Recurring-Secret": SECRET}
        )
        assert response.status_code == 200
        assert response.json() == {"created": 3}

    def test_run_with_wrong_secret_rejected(self, client: TestClient) -> None:
        response = client.post(
            f"{BASE_URL}/run", headers={"X-Recurring-Secret": "wrong"}
        )
        assert response.status_code == 403

    def test_run_without_secret_rejected(self, client: TestClient) -> None:
        response = client.post(f"{BASE_URL}/run")
        assert response.status_code == 403

    def test_run_rejected_when_secret_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # An unset server secret must fail closed even if a header is sent.
        monkeypatch.setattr(settings, "RECURRING_RUN_SECRET", "")
        gen = _client(StubRecurringService())
        client = next(gen)
        try:
            response = client.post(
                f"{BASE_URL}/run", headers={"X-Recurring-Secret": ""}
            )
            assert response.status_code == 403
        finally:
            next(gen, None)
