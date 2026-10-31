"""Compare statement lines with what the user already registered.

``match_lines`` is the pure core (no I/O, easy to test); ``StatementReconciler``
fetches the two ledgers a statement can overlap — transactions and card payments —
in ONE concurrent round trip for the whole date range, then delegates to it.
"""

import asyncio
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import NamedTuple

from app.shared.text_match import names_match
from app.shared.types import PaymentMethod, StatementLineKind, TransactionType, UserId
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import CardPaymentView
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import Transaction

from ..constants import RECONCILE_WINDOW_DAYS
from ..interfaces import StatementReconcilerABC
from ..models import ReconciledLine, ReconciliationResult, StatementLine


class _Record(NamedTuple):
    """A registered row a statement line may correspond to (transaction or payment)."""

    kind: StatementLineKind
    label: str
    day: date
    amount: Decimal
    card_name: str | None  # set for card payments
    is_credit: bool  # a transaction paid on credit (it carries a card)


class _Candidate(NamedTuple):
    """A possible (line, record) pairing, ordered so the best pairs sort first."""

    distance: int
    name_differs: bool
    card_differs: bool
    line_index: int
    record_index: int


def match_lines(
    lines: list[StatementLine],
    transactions: list[Transaction],
    payments: list[CardPaymentView],
    window_days: int,
) -> ReconciliationResult:
    """Split ``lines`` into those already registered and those missing.

    A line matches a record of the same kind with the EXACT same amount whose
    ``transaction_date`` / ``payment_date`` is within ``window_days`` (never the
    budget date). Matching is one-to-one and maximal: three identical lines
    against one record leave two missing, yet an early best-pair choice never
    strands a line that another free record could take. Best pairs win first:
    closest day, then similar name, then same card (an equal amount on another
    card still matches). A line WITHOUT a date is never matched (always missing):
    guessing "today" would pair it with an unrelated recent purchase.

    Known limits (the data is fetched once per statement range): the transaction
    listing is capped at ``SUMMARY_FETCH_LIMIT`` rows, so a very large or old
    statement can over-report missing lines; and a purchase registered in cuotas
    (installments) is stored with a different amount, so it shows as missing.
    """
    records = [*map(_from_transaction, transactions), *map(_from_payment, payments)]
    candidates = sorted(
        _Candidate(
            distance=abs((record.day - line.date).days),
            name_differs=not names_match(line.description, record.label),
            card_differs=not _same_card(line, record),
            line_index=line_index,
            record_index=record_index,
        )
        for line_index, line in enumerate(lines)
        if line.date is not None  # an undated line has nothing to be compared on
        for record_index, record in enumerate(records)
        if record.kind == line.kind
        and record.amount == line.amount
        and abs((record.day - line.date).days) <= window_days
    )

    assigned = _assign(candidates, len(lines))

    return ReconciliationResult(
        matched=[
            ReconciledLine(
                line=lines[line_index],
                matched_label=records[record_index].label,
                matched_date=records[record_index].day,
            )
            for line_index, record_index in sorted(assigned.items())
        ],
        missing=[line for index, line in enumerate(lines) if index not in assigned],
    )


def _assign(candidates: list[_Candidate], line_count: int) -> dict[int, int]:
    """One-to-one ``line index -> record index`` assignment of maximum size.

    The best pairs are taken first (``candidates`` is sorted best-first); then each
    still-unmatched line looks for an augmenting path (Kuhn's algorithm), moving an
    earlier line to its next-best free record, so a greedy early choice never leaves
    a line missing while a valid record is still free.
    """
    options: dict[int, list[int]] = defaultdict(list)
    for candidate in candidates:
        options[candidate.line_index].append(candidate.record_index)

    owner: dict[int, int] = {}  # record index -> line index
    matched_lines: set[int] = set()
    for candidate in candidates:
        if candidate.record_index not in owner and candidate.line_index not in matched_lines:
            owner[candidate.record_index] = candidate.line_index
            matched_lines.add(candidate.line_index)

    for line_index in range(line_count):
        if line_index not in matched_lines:
            _augment(line_index, options, owner, set())
    return {line_index: record_index for record_index, line_index in owner.items()}


def _augment(
    line_index: int,
    options: dict[int, list[int]],
    owner: dict[int, int],
    visited: set[int],
) -> bool:
    """Try to give ``line_index`` a record, re-homing the current owner if needed."""
    for record_index in options[line_index]:
        if record_index in visited:
            continue
        visited.add(record_index)
        if record_index not in owner or _augment(owner[record_index], options, owner, visited):
            owner[record_index] = line_index
            return True
    return False


def _same_card(line: StatementLine, record: _Record) -> bool:
    """Whether the record plausibly belongs to the line's card.

    Payments carry the card name; a transaction only knows it was charged to SOME
    card, so a credit transaction counts as the same card when the line names one.
    """
    if line.card is None:
        return False
    if record.card_name is not None:
        return names_match(line.card, record.card_name)
    return record.is_credit


def _from_transaction(transaction: Transaction) -> _Record:
    kind = (
        StatementLineKind.INCOME
        if transaction.transaction_type == TransactionType.INCOME
        else StatementLineKind.EXPENSE
    )
    return _Record(
        kind=kind,
        label=transaction.description,
        day=transaction.transaction_date,
        amount=transaction.amount,
        card_name=None,
        is_credit=transaction.payment_method == PaymentMethod.CREDITO,
    )


def _from_payment(payment: CardPaymentView) -> _Record:
    return _Record(
        kind=StatementLineKind.CARD_PAYMENT,
        label=payment.card_name,
        day=payment.payment_date,
        amount=payment.amount,
        card_name=payment.card_name,
        is_credit=False,
    )


class StatementReconciler(StatementReconcilerABC):
    """Reconciles statement lines against the user's transactions and card payments."""

    def __init__(
        self,
        transactions: TransactionServiceABC,
        cards: CreditCardServiceABC,
        window_days: int = RECONCILE_WINDOW_DAYS,
    ) -> None:
        self._transactions = transactions
        self._cards = cards
        self._window_days = window_days

    async def reconcile(
        self, user_id: UserId, lines: list[StatementLine]
    ) -> ReconciliationResult:
        if not lines:
            return ReconciliationResult()

        days = [line.date for line in lines if line.date is not None]
        if not days:  # nothing dated to compare: every line stays missing
            return ReconciliationResult(missing=lines)

        window = timedelta(days=self._window_days)
        period_start = min(days) - window
        period_end = max(days) + window

        # Two independent reads for the WHOLE statement range (not one per line).
        transactions, payments = await asyncio.gather(
            self._transactions.list_by_period(
                user_id,
                period_start=period_start,
                period_end=period_end,
                date_field="transaction_date",
            ),
            self._cards.list_payments(user_id, period_start, period_end),
        )
        return match_lines(lines, transactions, payments, self._window_days)
