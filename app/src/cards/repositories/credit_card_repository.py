"""Supabase-backed credit-card repository (data access only)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.exceptions import InfrastructureError
from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import parse_datetime as _parse_datetime
from app.shared.parsing import parse_decimal as _parse_decimal
from app.shared.serialization import decimal_to_db
from app.shared.types import CardId, UserId

from ..constants import CREDIT_CARDS_TABLE
from ..interfaces import CreditCardRepositoryABC
from ..models import CreditCard, CreditCardCreate

logger = get_logger(__name__)


class CreditCardRepository(CreditCardRepositoryABC):
    """Persists credit cards in Supabase via the database interface."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def create(self, card: CreditCardCreate, user_id: UserId) -> CreditCard:
        row = {
            "user_id": user_id,
            "name": card.name,
            "credit_limit": decimal_to_db(card.credit_limit),
            "cutoff_day": card.cutoff_day,
            "payment_day": card.payment_day,
            "is_active": True,
        }

        result = await self._db.insert(CREDIT_CARDS_TABLE, row)
        if not result.data:
            raise InfrastructureError(
                "Credit card insert returned no rows",
                code="CREDIT_CARD_INSERT_FAILED",
            )

        created = _row_to_card(result.data[0])
        logger.info("Credit card created", card_id=created.id, user_id=user_id)
        return created

    async def get_by_id(self, card_id: CardId, user_id: UserId) -> CreditCard | None:
        config = QueryConfig(filters={"id": card_id, "user_id": user_id}, limit=1)
        result = await self._db.select(CREDIT_CARDS_TABLE, config)
        if not result.data:
            return None
        return _row_to_card(result.data[0])

    async def list_active(self, user_id: UserId) -> list[CreditCard]:
        config = QueryConfig(
            filters={"user_id": user_id, "is_active": True},
            order_by="created_at",
            order_ascending=True,
        )
        result = await self._db.select(CREDIT_CARDS_TABLE, config)
        return [_row_to_card(row) for row in result.data]

    async def update(
        self,
        card_id: CardId,
        user_id: UserId,
        *,
        name: str | None = None,
        credit_limit: Decimal | None = None,
        cutoff_day: int | None = None,
        payment_day: int | None = None,
    ) -> CreditCard | None:
        changes: dict[str, Any] = {}
        if name is not None:
            changes["name"] = name
        if credit_limit is not None:
            changes["credit_limit"] = decimal_to_db(credit_limit)
        if cutoff_day is not None:
            changes["cutoff_day"] = cutoff_day
        if payment_day is not None:
            changes["payment_day"] = payment_day
        if not changes:
            return await self.get_by_id(card_id, user_id)

        result = await self._db.update(
            CREDIT_CARDS_TABLE, changes, {"id": card_id, "user_id": user_id}
        )
        if not result.data:
            return None
        updated = _row_to_card(result.data[0])
        logger.info("Credit card updated", card_id=card_id, user_id=user_id)
        return updated

    async def deactivate(self, card_id: CardId, user_id: UserId) -> CreditCard | None:
        # Soft delete: charges (transactions.card_id) and card_payments reference
        # this card, so we flag it inactive instead of removing the row.
        result = await self._db.update(
            CREDIT_CARDS_TABLE, {"is_active": False}, {"id": card_id, "user_id": user_id}
        )
        if not result.data:
            return None
        card = _row_to_card(result.data[0])
        logger.info("Credit card deactivated", card_id=card_id, user_id=user_id)
        return card


def _row_to_card(row: dict[str, Any]) -> CreditCard:
    """Map a raw database row to a domain ``CreditCard``."""
    return CreditCard(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        name=row["name"],
        credit_limit=_parse_decimal(row.get("credit_limit")),
        cutoff_day=int(row.get("cutoff_day") or 1),
        payment_day=int(row.get("payment_day") or 1),
        is_active=bool(row.get("is_active", True)),
        created_at=_parse_datetime(row.get("created_at")),
    )
