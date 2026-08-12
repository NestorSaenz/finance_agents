"""Supabase-backed recurring-template repository (data access only)."""

from datetime import date
from typing import Any

from app.core.exceptions import InfrastructureError, RecurringNotFoundError
from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import (
    parse_date as _parse_date,
)
from app.shared.parsing import (
    parse_datetime as _parse_datetime,
)
from app.shared.parsing import (
    parse_decimal as _parse_decimal,
)
from app.shared.parsing import (
    parse_enum as _parse_enum,
)
from app.shared.parsing import (
    parse_optional_date as _parse_optional_date,
)
from app.shared.serialization import decimal_to_db
from app.shared.types import PaymentMethod, TransactionType, UserId

from ..constants import DUE_PAGE_SIZE, RECURRING_TABLE
from ..interfaces import RecurringRepositoryABC
from ..models import RecurringCreate, RecurringFrequency, RecurringTransaction

logger = get_logger(__name__)


class RecurringRepository(RecurringRepositoryABC):
    """Persists recurring templates in Supabase via the database interface."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def create(
        self, rec: RecurringCreate, user_id: UserId
    ) -> RecurringTransaction:
        # The transactions table names the type column "type"; match it here so
        # both tables read the same way (mapped from the ``transaction_type`` field).
        row = {
            "user_id": user_id,
            "amount": decimal_to_db(rec.amount),
            "description": rec.description,
            "type": rec.transaction_type.value,
            "category": rec.category,
            "payment_method": rec.payment_method.value if rec.payment_method else None,
            "card_id": rec.card_id,
            "frequency": rec.frequency.value,
            "day_of_month": rec.day_of_month,
            "next_run_date": rec.next_run_date.isoformat(),
            "active": rec.active,
        }

        result = await self._db.insert(RECURRING_TABLE, row)
        if not result.data:
            raise InfrastructureError(
                "Recurring insert returned no rows", code="RECURRING_INSERT_FAILED"
            )

        created = _row_to_recurring(result.data[0])
        logger.info("Recurring created", recurring_id=created.id, user_id=user_id)
        return created

    async def get_by_id(
        self, recurring_id: str, user_id: UserId
    ) -> RecurringTransaction | None:
        config = QueryConfig(filters={"id": recurring_id, "user_id": user_id}, limit=1)
        result = await self._db.select(RECURRING_TABLE, config)
        if not result.data:
            return None
        return _row_to_recurring(result.data[0])

    async def list_for_user(self, user_id: UserId) -> list[RecurringTransaction]:
        config = QueryConfig(
            filters={"user_id": user_id},
            order_by="created_at",
            order_ascending=False,
        )
        result = await self._db.select(RECURRING_TABLE, config)
        return [_row_to_recurring(row) for row in result.data]

    async def list_due(self, as_of: date) -> list[RecurringTransaction]:
        # System path: scan ACTIVE templates of ALL users, then apply the
        # ``next_run_date <= as_of`` window in Python (PostgREST equality filters
        # can't express a range). Page through every row instead of one unbounded
        # fetch, so a large userbase's due set is never silently truncated (mirrors
        # TransactionService.get_spending_summary's paging).
        rows: list[dict[str, Any]] = []
        offset = 0
        while True:
            config = QueryConfig(
                filters={"active": True},
                limit=DUE_PAGE_SIZE,
                offset=offset,
                order_by="created_at",
                order_ascending=True,
            )
            result = await self._db.select(RECURRING_TABLE, config)
            rows.extend(result.data)
            if len(result.data) < DUE_PAGE_SIZE:
                break
            offset += DUE_PAGE_SIZE
        return [
            rec
            for row in rows
            if (rec := _row_to_recurring(row)).active and rec.next_run_date <= as_of
        ]

    async def update(
        self, recurring_id: str, user_id: UserId, data: dict[str, object]
    ) -> RecurringTransaction:
        result = await self._db.update(
            RECURRING_TABLE, data, {"id": recurring_id, "user_id": user_id}
        )
        if not result.data:
            raise RecurringNotFoundError(recurring_id)
        return _row_to_recurring(result.data[0])

    async def delete(self, recurring_id: str, user_id: UserId) -> None:
        # Scoped by user_id so a user can only delete their own templates.
        await self._db.delete(
            RECURRING_TABLE, {"id": recurring_id, "user_id": user_id}
        )


def _parse_optional_payment_method(value: object) -> PaymentMethod | None:
    """Map a raw DB value to a ``PaymentMethod`` (``None`` passes through)."""
    if value is None:
        return None
    return _parse_enum(PaymentMethod, value, PaymentMethod.EFECTIVO)


def _row_to_recurring(row: dict[str, Any]) -> RecurringTransaction:
    """Map a raw database row to a domain ``RecurringTransaction``."""
    category = row.get("category")
    card_id = row.get("card_id")
    return RecurringTransaction(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        amount=_parse_decimal(row.get("amount")),
        description=row["description"],
        transaction_type=_parse_enum(
            TransactionType, row.get("type"), TransactionType.EXPENSE
        ),
        category=str(category) if category else None,
        payment_method=_parse_optional_payment_method(row.get("payment_method")),
        card_id=str(card_id) if card_id else None,
        frequency=_parse_enum(
            RecurringFrequency, row.get("frequency"), RecurringFrequency.MONTHLY
        ),
        day_of_month=int(row.get("day_of_month", 1)),
        next_run_date=_parse_date(row.get("next_run_date")),
        last_run_date=_parse_optional_date(row.get("last_run_date")),
        active=bool(row.get("active", True)),
        created_at=_parse_datetime(row.get("created_at")),
    )
