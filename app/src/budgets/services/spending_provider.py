"""Computes spending from the transactions table for budget evaluation."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import parse_date as _parse_date
from app.shared.parsing import parse_decimal as _parse_decimal
from app.shared.types import Category, UserId
from app.src.transactions.constants import TRANSACTIONS_TABLE

from ..interfaces import BudgetSpendingABC
from ..models import BudgetSpending

logger = get_logger(__name__)


BUDGET_SPENDING_RPC: Final[str] = "budget_spending"


class TransactionSpendingProvider(BudgetSpendingABC):
    """Sums expense transactions for a user/category within a period.

    Prefers the server-side ``budget_spending`` Postgres function (migration 017):
    one aggregate query returning the total and its recurring ("fixed") part.
    Falls back to an in-Python scan if the function isn't present yet, so it works
    either way.
    """

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def get_spending(
        self,
        user_id: UserId,
        category: Category | None,
        period_start: date,
        period_end: date,
    ) -> BudgetSpending:
        category_value = category if category is not None else None
        try:
            result = await self._db.execute_rpc(
                BUDGET_SPENDING_RPC,
                {
                    "p_user_id": user_id,
                    "p_category": category_value,
                    "p_start": period_start.isoformat(),
                    "p_end": period_end.isoformat(),
                },
            )
            spending = _parse_spending(result.data)
            if spending is not None:
                return spending
        except Exception as e:  # noqa: BLE001 - RPC missing/unavailable -> fall back to scan.
            logger.warning("budget_spending RPC failed; falling back to scan", error=str(e))

        return await self._scan_in_python(user_id, category_value, period_start, period_end)

    async def _scan_in_python(
        self,
        user_id: UserId,
        category_value: str | None,
        period_start: date,
        period_end: date,
    ) -> BudgetSpending:
        """Fallback: fetch the user's expenses and sum the in-range ones."""
        filters: dict[str, Any] = {"user_id": user_id, "type": "expense"}
        if category_value is not None:
            filters["category"] = category_value

        config = QueryConfig(
            select="amount,transaction_date,budget_date,recurring_id", filters=filters
        )
        result = await self._db.select(TRANSACTIONS_TABLE, config)

        # Attribute by budget_date (credit -> payment month); older rows without
        # it fall back to transaction_date, matching the budget_spending SQL.
        in_range = [
            (_parse_decimal(row.get("amount")), row.get("recurring_id") is not None)
            for row in result.data
            if (
                impact := _parse_date(row.get("budget_date") or row.get("transaction_date"))
            )
            is not None
            and period_start <= impact <= period_end
        ]
        return BudgetSpending(
            total=sum((amount for amount, _ in in_range), start=Decimal("0")),
            fixed=sum((amount for amount, is_fixed in in_range if is_fixed), start=Decimal("0")),
        )


def _parse_spending(data: list[dict[str, Any]] | list[Any]) -> BudgetSpending | None:
    """Extract ``{total, fixed}`` from the RPC rows, or None if absent/malformed."""
    if not data:
        return None
    row = data[0]
    if not isinstance(row, dict):
        return None
    total = _to_decimal(row.get("total"))
    fixed = _to_decimal(row.get("fixed"))
    if total is None or fixed is None:
        return None
    return BudgetSpending(total=total, fixed=fixed)


def _to_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return number if number.is_finite() else None
