"""Re-dates a card's pending charges after its cutoff/payment day changes."""

import asyncio
from datetime import date
from typing import Any, Final

import httpx
from postgrest.exceptions import APIError

from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import parse_optional_date
from app.shared.types import PaymentMethod, UserId
from app.src.transactions.constants import INSTALLMENT_SUFFIX_RE, TRANSACTIONS_TABLE

from ..constants import BUDGET_SYNC_CONCURRENCY, BUDGET_SYNC_FETCH_LIMIT
from ..cycle import budget_date_for
from ..interfaces import CardBudgetDateSyncABC
from ..models import BudgetDateSync, CreditCard

logger = get_logger(__name__)

# Raw failures the Supabase/PostgREST client can raise (not wrapped by the client).
_DB_FAILURES: Final = (APIError, httpx.HTTPError)

_COLUMNS: Final[str] = "id,description,payment_method,transaction_date,budget_date"


class TransactionBudgetDateSync(CardBudgetDateSyncABC):
    """Recomputes ``budget_date`` on the transactions table for one card.

    One select, filtered in Python (PostgREST can't express the rules), then one
    update per row whose date actually changes. Idempotent: a second run finds
    every row already correct.
    """

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def resync(
        self, card: CreditCard, user_id: UserId, *, from_date: date
    ) -> BudgetDateSync:
        result = await self._db.select(
            TRANSACTIONS_TABLE,
            QueryConfig(
                select=_COLUMNS,
                filters={"user_id": user_id, "type": "expense", "card_id": card.id},
                # Newest first so the fetch cap can never drop the recent rows.
                order_by="transaction_date",
                order_ascending=False,
                limit=BUDGET_SYNC_FETCH_LIMIT,
            ),
        )
        changes = [
            (str(row["id"]), new_date)
            for row in result.data
            if (new_date := _new_budget_date(row, card, from_date)) is not None
        ]
        semaphore = asyncio.Semaphore(BUDGET_SYNC_CONCURRENCY)

        async def _bounded(tx_id: str, new_date: date) -> bool:
            async with semaphore:
                return await self._update_one(tx_id, new_date, card, user_id)

        outcomes = await asyncio.gather(*(_bounded(tx_id, d) for tx_id, d in changes))
        updated = sum(outcomes)
        return BudgetDateSync(updated=updated, failed=len(outcomes) - updated)

    async def _update_one(
        self, transaction_id: str, new_date: date, card: CreditCard, user_id: UserId
    ) -> bool:
        """Persist one row's new budget date; ``False`` when the write failed."""
        try:
            # card_id stays in the filter so a row unlinked meanwhile is not touched.
            await self._db.update(
                TRANSACTIONS_TABLE,
                {"budget_date": new_date.isoformat()},
                {"id": transaction_id, "user_id": user_id, "card_id": card.id},
            )
        except _DB_FAILURES as e:
            logger.error(
                "Could not re-date card charge",
                transaction_id=transaction_id,
                card_id=card.id,
                user_id=user_id,
                error=str(e),
            )
            return False
        return True


def _new_budget_date(row: dict[str, Any], card: CreditCard, from_date: date) -> date | None:
    """The corrected budget date for a pending credit charge, or ``None`` to skip it.

    Skipped: cash rows, installments (their budget month is their own date), rows
    already paid (budget date before ``from_date``), rows already correct.
    """
    transaction_date = parse_optional_date(row.get("transaction_date"))
    if transaction_date is None:
        return None
    if row.get("payment_method") == PaymentMethod.EFECTIVO:
        return None
    if INSTALLMENT_SUFFIX_RE.search(str(row.get("description") or "")):
        return None
    # Pending = not yet due by our records (budget_date >= from_date): a day change
    # mostly CORRECTS a misconfigured card, so rows of the old open cycle must be fixed too.
    current = parse_optional_date(row.get("budget_date")) or transaction_date
    if current < from_date:
        return None
    new_date = budget_date_for(card, transaction_date)
    return None if new_date == current else new_date
