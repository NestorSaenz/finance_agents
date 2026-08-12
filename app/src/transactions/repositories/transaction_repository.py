"""Supabase-backed transaction repository (data access only)."""

from typing import Any

from app.core.exceptions import InfrastructureError
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
from app.shared.serialization import decimal_to_db
from app.shared.types import (
    CardId,
    Category,
    CategoryType,
    CurrencyType,
    PaymentMethod,
    TransactionId,
    TransactionType,
    UserId,
)

from ..constants import DEFAULT_SOURCE, TRANSACTIONS_TABLE
from ..interfaces import TransactionRepositoryABC
from ..models import Transaction, TransactionCreate

logger = get_logger(__name__)


class TransactionRepository(TransactionRepositoryABC):
    """Persists transactions in Supabase via the database interface."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def create(self, transaction: TransactionCreate, user_id: UserId) -> Transaction:
        result = await self._db.insert(
            TRANSACTIONS_TABLE, _transaction_row(transaction, user_id)
        )
        if not result.data:
            raise InfrastructureError(
                "Transaction insert returned no rows",
                code="TRANSACTION_INSERT_FAILED",
            )

        created = _row_to_transaction(result.data[0])
        logger.info("Transaction created", transaction_id=created.id, user_id=user_id)
        return created

    async def create_occurrence(
        self, transaction: TransactionCreate, user_id: UserId
    ) -> Transaction | None:
        # Exactly-once insert: the unique index on (recurring_id, occurrence_date)
        # rejects a second row for the same scheduled occurrence, so a retried or
        # duplicated run is a silent no-op (empty result) rather than a double charge.
        row = _transaction_row(transaction, user_id)
        row["recurring_id"] = transaction.recurring_id
        row["occurrence_date"] = (
            transaction.occurrence_date.isoformat()
            if transaction.occurrence_date is not None
            else None
        )
        result = await self._db.insert_ignore_duplicates(
            TRANSACTIONS_TABLE, row, on_conflict="recurring_id,occurrence_date"
        )
        if not result.data:
            # Duplicate occurrence — already materialized on a prior run.
            return None
        created = _row_to_transaction(result.data[0])
        logger.info(
            "Recurring occurrence materialized",
            transaction_id=created.id,
            recurring_id=transaction.recurring_id,
            user_id=user_id,
        )
        return created

    async def get_by_id(
        self, transaction_id: TransactionId, user_id: UserId
    ) -> Transaction | None:
        config = QueryConfig(
            filters={"id": transaction_id, "user_id": user_id},
            limit=1,
        )
        result = await self._db.select(TRANSACTIONS_TABLE, config)
        if not result.data:
            return None
        return _row_to_transaction(result.data[0])

    async def list_page(
        self,
        user_id: UserId,
        *,
        limit: int,
        offset: int,
        transaction_type: TransactionType | None = None,
        category: Category | None = None,
        card_id: CardId | None = None,
    ) -> list[Transaction]:
        config = QueryConfig(
            filters=_build_filters(user_id, transaction_type, category, card_id),
            limit=limit,
            offset=offset,
            order_by="created_at",
            order_ascending=False,
        )
        result = await self._db.select(TRANSACTIONS_TABLE, config)
        return [_row_to_transaction(row) for row in result.data]

    async def count(
        self,
        user_id: UserId,
        *,
        transaction_type: TransactionType | None = None,
        category: Category | None = None,
        card_id: CardId | None = None,
    ) -> int:
        return await self._db.count(
            TRANSACTIONS_TABLE, _build_filters(user_id, transaction_type, category, card_id)
        )

    async def update(
        self, transaction_id: TransactionId, user_id: UserId, data: dict[str, object]
    ) -> Transaction:
        result = await self._db.update(
            TRANSACTIONS_TABLE, data, {"id": transaction_id, "user_id": user_id}
        )
        if not result.data:
            raise InfrastructureError(
                "Transaction update returned no rows", code="TRANSACTION_UPDATE_FAILED"
            )
        return _row_to_transaction(result.data[0])

    async def delete(self, transaction_id: TransactionId, user_id: UserId) -> None:
        # Scoped by user_id so a user can only delete their own transactions.
        await self._db.delete(TRANSACTIONS_TABLE, {"id": transaction_id, "user_id": user_id})

    async def recategorize(self, user_id: UserId, old: Category, new: Category) -> int:
        result = await self._db.update(
            TRANSACTIONS_TABLE, {"category": new}, {"user_id": user_id, "category": old}
        )
        return result.count or 0

    async def delete_by_category(self, user_id: UserId, category: Category) -> int:
        result = await self._db.delete(
            TRANSACTIONS_TABLE, {"user_id": user_id, "category": category}
        )
        return result.count or 0


def _transaction_row(transaction: TransactionCreate, user_id: UserId) -> dict[str, Any]:
    """Serialize a ``TransactionCreate`` to a transactions-table row."""
    return {
        "user_id": user_id,
        "amount": decimal_to_db(transaction.amount),  # str -> exact Postgres numeric.
        "currency": transaction.currency.value,
        "type": transaction.transaction_type.value,
        "description": transaction.description,
        "category": transaction.category or CategoryType.OTROS.value,
        "payment_method": (
            transaction.payment_method.value if transaction.payment_method else None
        ),
        "card_id": transaction.card_id,
        "transaction_date": transaction.transaction_date.isoformat(),
        # Defaults to the purchase date (cash/debit); credit sets its payment date.
        "budget_date": (
            transaction.budget_date or transaction.transaction_date
        ).isoformat(),
        "source": transaction.source,
    }


def _build_filters(
    user_id: UserId,
    transaction_type: TransactionType | None,
    category: Category | None,
    card_id: CardId | None = None,
) -> dict[str, Any]:
    """Build the equality filters for a user-scoped transaction query."""
    filters: dict[str, Any] = {"user_id": user_id}
    if transaction_type is not None:
        filters["type"] = transaction_type.value
    if category is not None:
        filters["category"] = category
    if card_id is not None:
        filters["card_id"] = card_id
    return filters


def _row_to_transaction(row: dict[str, Any]) -> Transaction:
    """Map a raw database row to a domain ``Transaction``."""
    return Transaction(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        amount=_parse_decimal(row.get("amount")),
        currency=_parse_enum(CurrencyType, row.get("currency"), CurrencyType.MXN),
        transaction_type=TransactionType(row["type"]),
        description=row["description"],
        # Preserve custom (non-enum) categories as stored; only NULL falls back.
        category=str(row.get("category") or CategoryType.OTROS.value),
        payment_method=_parse_payment_method(row.get("payment_method")),
        card_id=(str(row["card_id"]) if row.get("card_id") else None),
        transaction_date=_parse_date(row.get("transaction_date")),
        # Older rows (pre-migration 010) have no budget_date -> use purchase date.
        budget_date=_parse_date(row.get("budget_date") or row.get("transaction_date")),
        source=row.get("source") or DEFAULT_SOURCE,
        created_at=_parse_datetime(row.get("created_at")),
    )


def _parse_payment_method(value: object) -> PaymentMethod | None:
    """Payment method is optional; ``None`` stays ``None`` (unknown)."""
    return None if value is None else _parse_enum(PaymentMethod, value, PaymentMethod.EFECTIVO)


