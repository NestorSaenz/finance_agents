"""Contract (ABC) for the financial analysis module."""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal

from app.shared.types import UserId

from .models import FinancialSnapshot, MonthlyTotals, MovementCandidate


class AnalysisServiceABC(ABC):
    """Contract for building a holistic financial snapshot."""

    @abstractmethod
    async def snapshot(
        self, user_id: UserId, period: str, today: date | None = None
    ) -> FinancialSnapshot:
        """Aggregate the user's finances for ``period`` into a snapshot.

        ``today`` anchors the period boundaries to the user's local day; ``None``
        keeps the service pure and falls back to UTC (its default reference).
        """

    @abstractmethod
    async def monthly_trend(
        self, user_id: UserId, months: int, today: date | None = None
    ) -> list[MonthlyTotals]:
        """Income/expenses per calendar month for the last ``months``, oldest first.

        The window ends in ``today``'s month (``None`` → UTC) and ``months`` is
        clamped to the module's trend bounds. Months are bucketed by
        ``transaction_date`` — "when did I spend" — matching every other spending
        figure the assistant reports for a month.
        """

    @abstractmethod
    async def accumulated_surplus(self, user_id: UserId, as_of: date) -> Decimal:
        """Return free (unearmarked) cash accumulated up to ``as_of``.

        ``Σ(registered income) − Σ(cash expenses) − Σ(card payments) −
        Σ(goal contributions)`` over all history up to the month-end. It carries
        over month to month (no reset) and drops as the user spends or saves.
        """


class MovementFinderServiceABC(ABC):
    """Contract for unified movement search across the ledgers."""

    @abstractmethod
    async def find_movements(
        self,
        user_id: UserId,
        *,
        amount: Decimal | None = None,
        on_date: date | None = None,
        text: str | None = None,
        today: date | None = None,
    ) -> list[MovementCandidate]:
        """Find movements matching amount/date/text across all three ledgers.

        Searches transactions, card payments and goal contributions concurrently
        and returns typed candidates (newest first) so the agent can confirm and
        delete via the right tool. ``amount`` or ``text`` is a selective filter
        (searched over all history, bounded only by each service's fetch limit);
        a date alone scopes to that calendar month. At least one filter should be
        given (an all-empty query returns everything recent).
        """
