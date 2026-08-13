"""Unified movement search across the transaction, card and goal ledgers.

A movement the user sees in the dashboard can be a transaction, a card payment
or a goal contribution — three separate tables. ``delete_transaction`` only
searches transactions, so an aporte a meta is never found by it ("no encontré
ese movimiento"). This finder fans out over the three sources CONCURRENTLY (like
``AnalysisService``'s snapshot) and returns typed candidates, so the agent can
confirm and route deletion to the right tool. Read-only: it never mutates.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Final

from app.shared.text_match import contains_normalized, names_match
from app.shared.types import MovementKind, TransactionType, UserId
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import CardPaymentView
from app.src.goals.interfaces import GoalServiceABC
from app.src.goals.models import GoalContributionView
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import Transaction

from ..interfaces import MovementFinderServiceABC
from ..models import MovementCandidate

# A specific amount is a strong, near-unique key, so it is searched over ALL
# history; text/date-only queries scan a recent window instead.
_EPOCH: Final[date] = date(1970, 1, 1)
_FAR_FUTURE: Final[date] = date(2999, 12, 31)
_ONE_DAY: Final[timedelta] = timedelta(days=1)


class MovementFinder(MovementFinderServiceABC):
    """Finds movements across the three ledgers for the agent to act on."""

    def __init__(
        self,
        transactions: TransactionServiceABC,
        cards: CreditCardServiceABC,
        goals: GoalServiceABC,
    ) -> None:
        self._transactions = transactions
        self._cards = cards
        self._goals = goals

    async def find_movements(
        self,
        user_id: UserId,
        *,
        amount: Decimal | None = None,
        on_date: date | None = None,
        text: str | None = None,
        today: date | None = None,
    ) -> list[MovementCandidate]:
        reference = today or datetime.now(UTC).date()
        start, end = _search_window(amount, on_date, text, reference)

        # Independent reads → fetch concurrently (latency ≈ the slowest, not the
        # sum), mirroring AnalysisService.snapshot. All three are user-scoped.
        txs, payments, contributions = await asyncio.gather(
            self._transactions.list_by_period(
                user_id, period_start=start, period_end=end
            ),
            self._cards.list_payments(user_id, start, end),
            self._goals.list_contributions_in_period(user_id, start, end),
        )

        entries: list[tuple[MovementCandidate, str]] = [
            *((_from_transaction(t), _tx_search(t)) for t in txs),
            *((_from_payment(p), p.card_name) for p in payments),
            *((_from_contribution(c), c.goal_name) for c in contributions),
        ]
        matched = [
            candidate
            for candidate, search in entries
            if _matches(candidate, search, amount, on_date, text)
        ]
        matched.sort(key=lambda c: c.date, reverse=True)
        return matched


def _search_window(
    amount: Decimal | None,
    on_date: date | None,
    text: str | None,
    reference: date,
) -> tuple[date, date]:
    """The date window to search, by the strongest filter available.

    An ``amount`` or a ``text`` is itself a selective filter → search all history
    so an older movement is still found. A date ALONE scopes to that calendar
    month; an empty query (guarded by the tool) falls back to a recent window.
    """
    if amount is not None or text is not None:
        return _EPOCH, _FAR_FUTURE
    if on_date is not None:
        return on_date.replace(day=1), _month_end(on_date)
    return _month_start(_previous_month(reference)), _month_end(reference)


def _matches(
    candidate: MovementCandidate,
    search_text: str,
    amount: Decimal | None,
    on_date: date | None,
    text: str | None,
) -> bool:
    """Filter a candidate by the given amount/date/text criteria."""
    if amount is not None and candidate.amount != amount:
        return False
    # Date narrows only when there's no amount: the amount is the strong key, so
    # a misremembered date shouldn't hide the right-amount movement.
    if amount is None and on_date is not None and candidate.date != on_date:
        return False
    if text and not (
        contains_normalized(text, search_text) or names_match(text, search_text)
    ):
        return False
    return True


def _from_transaction(transaction: Transaction) -> MovementCandidate:
    kind = (
        MovementKind.INCOME
        if transaction.transaction_type == TransactionType.INCOME
        else MovementKind.EXPENSE
    )
    return MovementCandidate(
        kind=kind,
        label=transaction.description,
        amount=transaction.amount,
        date=transaction.transaction_date,
    )


def _from_payment(payment: CardPaymentView) -> MovementCandidate:
    return MovementCandidate(
        kind=MovementKind.CARD_PAYMENT,
        label=payment.card_name,
        amount=payment.amount,
        date=payment.payment_date,
    )


def _from_contribution(contribution: GoalContributionView) -> MovementCandidate:
    # A negative contribution is a retiro; expose the positive magnitude and let
    # the kind carry the direction (as the dashboard's movements list does).
    kind = (
        MovementKind.GOAL_WITHDRAWAL
        if contribution.amount < 0
        else MovementKind.GOAL_CONTRIBUTION
    )
    return MovementCandidate(
        kind=kind,
        label=contribution.goal_name,
        amount=abs(contribution.amount),
        date=contribution.contribution_date,
    )


def _tx_search(transaction: Transaction) -> str:
    """Searchable text for a transaction: its description plus its category."""
    return f"{transaction.description} {transaction.category or ''}".strip()


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    return _month_start(_next_month(day)) - _ONE_DAY


def _previous_month(day: date) -> date:
    first = day.replace(day=1)
    return (first - _ONE_DAY).replace(day=1)


def _next_month(day: date) -> date:
    if day.month == 12:
        return day.replace(year=day.year + 1, month=1, day=1)
    return day.replace(month=day.month + 1, day=1)
