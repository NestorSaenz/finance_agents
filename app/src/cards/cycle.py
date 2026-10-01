"""Billing-cycle math for credit cards.

Given a statement cutoff day and today's date, computes the current OPEN cycle
(the period whose expenses will land on the next statement), the due date of the
statement closing on a given cutoff, and the next UPCOMING payment (which may
belong to an already-closed statement). Days beyond a month's length clamp to
the last day (e.g. cutoff 31 in February -> Feb 28/29).
"""

import calendar
from datetime import date, timedelta
from typing import NamedTuple


def _day_in_month(year: int, month: int, day: int) -> date:
    """Return ``day`` of the given month, clamped to the month's last day."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _add_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _sub_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def compute_cycle(cutoff_day: int, today: date) -> tuple[date, date]:
    """Return (cycle_start, cycle_end) for the open statement cycle.

    The open cycle runs from the day AFTER the previous cutoff to the NEXT
    cutoff on/after today. Example: cutoff 15, today Jul 3 -> (Jun 16, Jul 15).
    """
    this_cutoff = _day_in_month(today.year, today.month, cutoff_day)
    if today <= this_cutoff:
        cycle_end = this_cutoff
        py, pm = _sub_month(today.year, today.month)
        prev_cutoff = _day_in_month(py, pm, cutoff_day)
    else:
        ny, nm = _add_month(today.year, today.month)
        cycle_end = _day_in_month(ny, nm, cutoff_day)
        prev_cutoff = this_cutoff
    return prev_cutoff + timedelta(days=1), cycle_end


def next_payment_date(payment_day: int, cycle_end: date) -> date:
    """Return the due date of the statement that closes at ``cycle_end``.

    Payment falls on ``payment_day`` in the first month whose payment day is
    strictly after the cutoff (typically the month after the cutoff).

    NOTE: this is NOT "the next payment the user has to make". It answers
    "when is the statement closing on ``cycle_end`` paid?" — which is exactly
    what a purchase's budget date needs (the statement CONTAINING the purchase).
    An earlier, already-closed statement may still be due before this date; use
    ``upcoming_payment`` for the next upcoming due date. Don't unify the two.
    """
    candidate = _day_in_month(cycle_end.year, cycle_end.month, payment_day)
    if candidate > cycle_end:
        return candidate
    ny, nm = _add_month(cycle_end.year, cycle_end.month)
    return _day_in_month(ny, nm, payment_day)


def payment_date_in_month(payment_day: int, month_end: date) -> date:
    """The payment date that falls inside ``month_end``'s calendar month.

    What a month view means by "fecha de pago": the day the user pays that card
    during that month (``payment_day``, clamped to the month's length), whichever
    statement it settles.
    """
    return _day_in_month(month_end.year, month_end.month, payment_day)


class UpcomingPayment(NamedTuple):
    """The next payment due on/after a day, and the statement it settles.

    ``statement_closed`` is True when the due date belongs to a statement whose
    cutoff already passed (its amount is final); False when it belongs to the
    still-OPEN cycle (the previous statement's due date already passed, and
    this one keeps accumulating charges until ``statement_end``).
    """

    due_date: date
    statement_start: date
    statement_end: date
    statement_closed: bool


def upcoming_payment(cutoff_day: int, payment_day: int, today: date) -> UpcomingPayment:
    """Return the next payment due on/after ``today`` and its statement period.

    The last closed statement (cutoff before the open cycle) is still due when
    its due date is today or later; otherwise the next due date is the open
    cycle's. Example: cutoff 19, payment 2, today Oct 1 -> the Aug 20–Sep 19
    statement, due Oct 2 (not the open cycle's Nov 2).
    """
    cycle_start, cycle_end = compute_cycle(cutoff_day, today)
    last_cutoff = cycle_start - timedelta(days=1)
    closed_due = next_payment_date(payment_day, last_cutoff)
    if closed_due >= today:
        closed_start, _ = compute_cycle(cutoff_day, last_cutoff)
        return UpcomingPayment(closed_due, closed_start, last_cutoff, statement_closed=True)
    return UpcomingPayment(
        next_payment_date(payment_day, cycle_end),
        cycle_start,
        cycle_end,
        statement_closed=False,
    )
