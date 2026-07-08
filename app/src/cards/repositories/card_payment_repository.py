"""Supabase-backed credit-card payment repository (data access only)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Final

from app.core.exceptions import InfrastructureError
from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import parse_date as _parse_date
from app.shared.parsing import parse_datetime as _parse_datetime
from app.shared.parsing import parse_decimal as _parse_decimal
from app.shared.serialization import decimal_to_db
from app.shared.types import CardId, UserId

from ..interfaces import CardPaymentRepositoryABC
from ..models import CardPayment, CardPaymentCreate

logger = get_logger(__name__)

CARD_PAYMENTS_TABLE: Final[str] = "card_payments"


class CardPaymentRepository(CardPaymentRepositoryABC):
    """Persists credit-card payments in Supabase."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def create(
        self, payment: CardPaymentCreate, card_id: CardId, user_id: UserId
    ) -> CardPayment:
        row = {
            "user_id": user_id,
            "card_id": card_id,
            "amount": decimal_to_db(payment.amount),
            "payment_date": payment.payment_date.isoformat(),
        }
        result = await self._db.insert(CARD_PAYMENTS_TABLE, row)
        if not result.data:
            raise InfrastructureError(
                "Card payment insert returned no rows",
                code="CARD_PAYMENT_INSERT_FAILED",
            )
        created = _row_to_payment(result.data[0])
        logger.info("Card payment created", card_id=card_id, user_id=user_id)
        return created

    async def total_paid(self, user_id: UserId, card_id: CardId) -> Decimal:
        config = QueryConfig(
            select="amount", filters={"user_id": user_id, "card_id": card_id}
        )
        result = await self._db.select(CARD_PAYMENTS_TABLE, config)
        return sum((_parse_decimal(r.get("amount")) for r in result.data), Decimal("0"))

    async def list_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPayment]:
        config = QueryConfig(
            filters={"user_id": user_id},
            order_by="payment_date",
            order_ascending=False,
        )
        result = await self._db.select(CARD_PAYMENTS_TABLE, config)
        payments = [_row_to_payment(row) for row in result.data]
        # Date range applied in Python (PostgREST equality filters can't do ranges).
        return [p for p in payments if period_start <= p.payment_date <= period_end]


def _row_to_payment(row: dict[str, Any]) -> CardPayment:
    return CardPayment(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        card_id=str(row["card_id"]),
        amount=_parse_decimal(row.get("amount")),
        payment_date=_parse_date(row.get("payment_date")),
        created_at=_parse_datetime(row.get("created_at")),
    )
