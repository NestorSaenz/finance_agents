"""Unit tests for the credit-card payment repository (Supabase mocked)."""

from datetime import date
from decimal import Decimal

import pytest

from app.src.cards.repositories.card_payment_repository import CardPaymentRepository
from tests.fakes import FakeDatabase

pytestmark = pytest.mark.asyncio


def _row(payment_date: str, amount: float, card_id: str = "card-1") -> dict[str, object]:
    return {
        "id": f"pay-{payment_date}",
        "user_id": "u1",
        "card_id": card_id,
        "amount": amount,
        "payment_date": payment_date,
        "created_at": "2026-07-01T10:00:00+00:00",
    }


async def test_total_paid_up_to_sums_all_cards_on_or_before_as_of() -> None:
    # Payments across two different cards; the August one is excluded at July-end.
    db = FakeDatabase(
        rows=[
            _row("2026-07-05", 100000.0, card_id="card-1"),
            _row("2026-07-20", 50000.0, card_id="card-2"),
            _row("2026-08-02", 25000.0, card_id="card-1"),
        ]
    )
    repo = CardPaymentRepository(db)  # type: ignore[arg-type]

    total = await repo.total_paid_up_to("u1", date(2026, 7, 31))

    assert total == Decimal("150000")  # 100k + 50k, August payment excluded


async def test_total_paid_up_to_is_zero_without_payments() -> None:
    repo = CardPaymentRepository(FakeDatabase(rows=[]))  # type: ignore[arg-type]

    assert await repo.total_paid_up_to("u1", date(2026, 7, 31)) == Decimal("0")
