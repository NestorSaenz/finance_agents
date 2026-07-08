"""Computes spending from the transactions table for budget evaluation."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import parse_date as _parse_date
from app.shared.parsing import parse_decimal as _parse_decimal
from app.shared.types import Category, UserId
from app.src.transactions.constants import TRANSACTIONS_TABLE

from ..interfaces import BudgetSpendingABC

logger = get_logger(__name__)


SUM_EXPENSES_RPC = "sum_expenses"


class TransactionSpendingProvider(BudgetSpendingABC):
    """Sums expense transactions for a user/category within a period.

    Prefers the server-side ``sum_expenses`` Postgres function (migration 005):
    one aggregate query instead of fetching every row. Falls back to an
    in-Python sum if the function isn't present yet, so it works either way.
    """

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def get_spent(
        self,
        user_id: UserId,
        category: Category | None,
        period_start: date,
        period_end: date,
    ) -> Decimal:
        category_value = category if category is not None else None
        try:
            result = await self._db.execute_rpc(
                SUM_EXPENSES_RPC,
                {
                    "p_user_id": user_id,
                    "p_category": category_value,
                    "p_start": period_start.isoformat(),
                    "p_end": period_end.isoformat(),
                },
            )
            total = _scalar(result.data)
            if total is not None:
                return total
        except Exception as e:  # noqa: BLE001 - RPC missing/unavailable -> fall back to scan.
            logger.warning("sum_expenses RPC failed; falling back to scan", error=str(e))

        return await self._sum_in_python(user_id, category_value, period_start, period_end)

    async def _sum_in_python(
        self,
        user_id: UserId,
        category_value: str | None,
        period_start: date,
        period_end: date,
    ) -> Decimal:
        """Fallback: fetch the user's expenses and sum the in-range ones."""
        filters: dict[str, Any] = {"user_id": user_id, "type": "expense"}
        if category_value is not None:
            filters["category"] = category_value

        config = QueryConfig(select="amount,transaction_date", filters=filters)
        result = await self._db.select(TRANSACTIONS_TABLE, config)

        total = Decimal("0")
        for row in result.data:
            tx_date = _parse_date(row.get("transaction_date"))
            if tx_date is not None and period_start <= tx_date <= period_end:
                total += _parse_decimal(row.get("amount"))
        return total


def _scalar(data: list[dict[str, Any]] | list[Any]) -> Decimal | None:
    """Extract the numeric result of the sum_expenses RPC, or None if absent."""
    if not data:
        return None
    value = data[0]
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
