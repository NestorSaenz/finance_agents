"""Unit tests for the credit-card toolkit (service mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.agents.tools.card_tools import CardToolkit
from app.shared.types import CardId, UserId
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import (
    CardPayment,
    CardPaymentCreate,
    CardPaymentView,
    CreditCard,
    CreditCardCreate,
    CreditCardStatus,
)

pytestmark = pytest.mark.asyncio


def _card(name: str = "Visa BBVA") -> CreditCard:
    return CreditCard(
        id="card-1",
        user_id="u1",
        name=name,
        credit_limit=Decimal("5000000"),
        cutoff_day=15,
        payment_day=5,
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _status(card: CreditCard) -> CreditCardStatus:
    return CreditCardStatus(
        card=card,
        cycle_start=date(2026, 6, 16),
        cycle_end=date(2026, 7, 15),
        spent_cycle=Decimal("200000"),
        balance=Decimal("500000"),
        available=Decimal("4500000"),
        utilization=10.0,
        next_payment_date=date(2026, 8, 5),
    )


class FakeCardService(CreditCardServiceABC):
    def __init__(self, cards: list[CreditCard] | None = None) -> None:
        self.created: list[CreditCardCreate] = []
        self.payments: list[tuple[str, Decimal]] = []
        self._cards = cards if cards is not None else [_card()]

    async def create_card(self, card: CreditCardCreate, user_id: UserId) -> CreditCard:
        self.created.append(card)
        return _card(card.name)

    async def list_cards(self, user_id: UserId) -> list[CreditCard]:
        return self._cards

    async def get_all_status(
        self, user_id: UserId, as_of: date | None = None
    ) -> list[CreditCardStatus]:
        return [_status(c) for c in self._cards]

    async def get_status(
        self, card_id: CardId, user_id: UserId, as_of: date | None = None
    ) -> CreditCardStatus:
        return _status(self._cards[0])

    async def register_payment(
        self, card_id: CardId, user_id: UserId, payment: CardPaymentCreate
    ) -> CardPayment:
        self.payments.append((card_id, payment.amount))
        return CardPayment(
            id="pay-1",
            user_id=user_id,
            card_id=card_id,
            amount=payment.amount,
            payment_date=payment.payment_date,
            created_at=datetime(2026, 7, 3, tzinfo=UTC),
        )

    async def resolve_by_name(self, name: str, user_id: UserId) -> CreditCard | None:
        target = name.lower()
        return next((c for c in self._cards if target in c.name.lower()), None)

    async def list_payments(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPaymentView]:
        return []

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
        self.updated: dict[str, object] = {
            "name": name,
            "credit_limit": credit_limit,
            "cutoff_day": cutoff_day,
            "payment_day": payment_day,
        }
        base = self._cards[0]
        return base.model_copy(
            update={k: v for k, v in self.updated.items() if v is not None}
        )

    async def delete_card(self, card_id: CardId, user_id: UserId) -> CreditCard:
        self.deleted: str = card_id
        return self._cards[0].model_copy(update={"is_active": False})


async def test_create_card() -> None:
    service = FakeCardService()
    result = await CardToolkit(service).dispatch(
        "create_card",
        {"name": "Visa BBVA", "credit_limit": 5000000, "cutoff_day": 15, "payment_day": 5},
        "u1",
    )
    assert service.created[0].name == "Visa BBVA"
    assert service.created[0].cutoff_day == 15
    assert "Visa BBVA" in result


async def test_create_card_invalid_days() -> None:
    service = FakeCardService()
    result = await CardToolkit(service).dispatch(
        "create_card",
        {"name": "X", "credit_limit": 100, "cutoff_day": 40, "payment_day": 5},
        "u1",
    )
    assert not service.created
    assert "no pude" in result.lower()


async def test_query_cards_shows_balance_and_available() -> None:
    result = await CardToolkit(FakeCardService()).dispatch("query_cards", {}, "u1")
    assert "Visa BBVA" in result
    assert "500000" in result and "4500000" in result


async def test_pay_card_resolves_by_name() -> None:
    service = FakeCardService()
    result = await CardToolkit(service).dispatch(
        "pay_card", {"card_name": "visa", "amount": 300000}, "u1"
    )
    assert service.payments[0] == ("card-1", Decimal("300000"))
    assert "300000" in result


async def test_pay_unknown_card_returns_message() -> None:
    service = FakeCardService(cards=[_card(name="Mastercard")])
    result = await CardToolkit(service).dispatch(
        "pay_card", {"card_name": "Amex", "amount": 100}, "u1"
    )
    assert not service.payments
    assert "no encontré" in result.lower()


async def test_update_card_changes_limit() -> None:
    service = FakeCardService()
    result = await CardToolkit(service).dispatch(
        "update_card", {"card_name": "visa", "new_credit_limit": 8000000}, "u1"
    )
    assert service.updated["credit_limit"] == Decimal("8000000")
    assert "8000000" in result


async def test_update_card_ignores_invalid_day() -> None:
    service = FakeCardService()
    await CardToolkit(service).dispatch(
        "update_card",
        {"card_name": "visa", "new_name": "Visa Oro", "new_cutoff_day": 40},
        "u1",
    )
    # Out-of-range day is dropped; the valid field still goes through.
    assert service.updated["cutoff_day"] is None
    assert service.updated["name"] == "Visa Oro"


async def test_update_card_no_fields_asks() -> None:
    service = FakeCardService()
    result = await CardToolkit(service).dispatch("update_card", {"card_name": "visa"}, "u1")
    assert not hasattr(service, "updated")
    assert "¿qué quieres cambiar" in result.lower()


async def test_update_unknown_card_returns_message() -> None:
    service = FakeCardService(cards=[_card(name="Mastercard")])
    result = await CardToolkit(service).dispatch(
        "update_card", {"card_name": "Amex", "new_credit_limit": 100}, "u1"
    )
    assert not hasattr(service, "updated")
    assert "no encontré" in result.lower()


async def test_delete_card_soft_deletes() -> None:
    service = FakeCardService()
    result = await CardToolkit(service).dispatch("delete_card", {"card_name": "visa"}, "u1")
    assert service.deleted == "card-1"
    assert "eliminé" in result.lower()


async def test_delete_unknown_card_returns_message() -> None:
    service = FakeCardService(cards=[_card(name="Mastercard")])
    result = await CardToolkit(service).dispatch("delete_card", {"card_name": "Amex"}, "u1")
    assert not hasattr(service, "deleted")
    assert "no encontré" in result.lower()
