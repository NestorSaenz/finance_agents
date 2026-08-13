"""Integration tests for the /cards endpoints (service overridden)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import CardNotFoundError
from app.main import app
from app.shared.types import CardId, UserId
from app.src.cards.dependencies import get_credit_card_service
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import (
    CardPayment,
    CardPaymentCreate,
    CardPaymentView,
    CreditCard,
    CreditCardCreate,
    CreditCardStatus,
)

BASE_URL = "/api/v1/cards"


def _card() -> CreditCard:
    return CreditCard(
        id="card-1",
        user_id="demo-user",
        name="Visa BBVA",
        credit_limit=Decimal("5000000"),
        cutoff_day=15,
        payment_day=5,
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _status() -> CreditCardStatus:
    return CreditCardStatus(
        card=_card(),
        cycle_start=date(2026, 6, 16),
        cycle_end=date(2026, 7, 15),
        spent_cycle=Decimal("200000"),
        balance=Decimal("500000"),
        available=Decimal("4500000"),
        utilization=10.0,
        next_payment_date=date(2026, 8, 5),
    )


class StubCardService(CreditCardServiceABC):
    def __init__(self, found: bool = True) -> None:
        self.found = found

    async def create_card(self, card: CreditCardCreate, user_id: UserId) -> CreditCard:
        return _card()

    async def list_cards(self, user_id: UserId) -> list[CreditCard]:
        return [_card()]

    async def get_all_status(
        self, user_id: UserId, as_of: date | None = None, **kwargs: object
    ) -> list[CreditCardStatus]:
        return [_status()]

    async def get_status(
        self, card_id: CardId, user_id: UserId, as_of: date | None = None
    ) -> CreditCardStatus:
        return _status()

    async def total_paid_up_to(self, user_id: UserId, as_of: date) -> Decimal:
        return Decimal("0")

    async def register_payment(
        self, card_id: CardId, user_id: UserId, payment: CardPaymentCreate
    ) -> CardPayment:
        if not self.found:
            raise CardNotFoundError(card_id)
        return CardPayment(
            id="pay-1",
            user_id=user_id,
            card_id=card_id,
            amount=payment.amount,
            payment_date=payment.payment_date,
            created_at=datetime(2026, 7, 3, tzinfo=UTC),
        )

    async def resolve_by_name(self, name: str, user_id: UserId) -> CreditCard | None:
        return _card()

    async def remove_payment(
        self,
        user_id: UserId,
        amount: Decimal,
        *,
        payment_date: date | None = None,
        card_id: CardId | None = None,
    ) -> CardPayment | None:
        if not self.found:
            return None
        return CardPayment(
            id="pay-1",
            user_id=user_id,
            card_id=card_id or "card-1",
            amount=amount,
            payment_date=payment_date or date(2026, 7, 3),
            created_at=datetime(2026, 7, 3, tzinfo=UTC),
        )

    async def update_card(
        self,
        card_id: CardId,
        user_id: UserId,
        *,
        name: str | None = None,
        credit_limit: Decimal | None = None,
        cutoff_day: int | None = None,
        payment_day: int | None = None,
    ) -> CreditCard:
        if not self.found:
            raise CardNotFoundError(card_id)
        return _card()

    async def delete_card(self, card_id: CardId, user_id: UserId) -> CreditCard:
        if not self.found:
            raise CardNotFoundError(card_id)
        return _card()

    async def list_payments(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPaymentView]:
        return [
            CardPaymentView(
                card_name="Visa BBVA",
                amount=Decimal("100000"),
                payment_date=date(2026, 7, 3),
            )
        ]


def _client(service: CreditCardServiceABC) -> Iterator[TestClient]:
    app.dependency_overrides[get_credit_card_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from _client(StubCardService())


class TestCards:
    def test_create_card(self, client: TestClient) -> None:
        response = client.post(
            BASE_URL,
            json={
                "name": "Visa BBVA",
                "credit_limit": 5000000,
                "cutoff_day": 15,
                "payment_day": 5,
            },
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Visa BBVA"

    def test_rejects_invalid_cutoff_day(self, client: TestClient) -> None:
        response = client.post(
            BASE_URL,
            json={"name": "X", "credit_limit": 100, "cutoff_day": 40, "payment_day": 5},
        )
        assert response.status_code == 422

    def test_status_lists_cards(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/status")
        assert response.status_code == 200
        body = response.json()
        assert body["total_limit"] == "5000000"
        assert body["total_balance"] == "500000"
        assert body["cards"][0]["available"] == "4500000"

    def test_register_payment(self, client: TestClient) -> None:
        response = client.post(f"{BASE_URL}/card-1/payments", json={"amount": 300000})
        assert response.status_code == 200
        assert response.json()["card"]["id"] == "card-1"

    def test_list_payments(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/payments", params={"period": "este_mes"})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == "100000"
        assert body["payments"][0]["card_name"] == "Visa BBVA"

    def test_payment_missing_card_returns_404(self) -> None:
        gen = _client(StubCardService(found=False))
        client = next(gen)
        try:
            response = client.post(f"{BASE_URL}/nope/payments", json={"amount": 100})
            assert response.status_code == 404
        finally:
            next(gen, None)
