"""Computes how much was charged to a card from the transactions table."""

from datetime import date
from decimal import Decimal

from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import parse_date as _parse_date
from app.shared.parsing import parse_decimal as _parse_decimal
from app.shared.types import CardId, UserId
from app.src.transactions.constants import TRANSACTIONS_TABLE

from ..constants import CYCLE_FETCH_LIMIT
from ..interfaces import CreditCardSpendingABC

logger = get_logger(__name__)


class TransactionCardSpendingProvider(CreditCardSpendingABC):
    """Sums the expenses charged to a specific card within a cycle."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def charges_summary(
        self,
        user_id: UserId,
        card_id: CardId,
        cycle_start: date,
        as_of: date,
        period: tuple[date, date] | None = None,
    ) -> tuple[Decimal, Decimal, Decimal]:
        # Fetch the card's charges ONCE (equality filters server-side; date
        # windows applied in Python since PostgREST filters can't do ranges),
        # then derive the running total, the current-cycle total, and the
        # optional selected-period total from the same rows.
        config = QueryConfig(
            select="amount,transaction_date",
            filters={"user_id": user_id, "type": "expense", "card_id": card_id},
            limit=CYCLE_FETCH_LIMIT,
        )
        result = await self._db.select(TRANSACTIONS_TABLE, config)

        total = cycle = period_total = Decimal("0")
        for row in result.data:
            tx_date = _parse_date(row.get("transaction_date"))
            if tx_date is None:
                continue
            amount = _parse_decimal(row.get("amount"))
            if tx_date <= as_of:
                total += amount
                if tx_date >= cycle_start:
                    cycle += amount
            if period is not None and period[0] <= tx_date <= period[1]:
                period_total += amount
        return total, cycle, period_total
