"""Billing-cycle math for credit cards.

Given a statement cutoff day and today's date, computes the current OPEN cycle
(the period whose expenses will land on the next statement) and the next payment
due date. Days beyond a month's length clamp to the last day (e.g. cutoff 31 in
February -> Feb 28/29).
"""

import calendar
from datetime import date, timedelta


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
    """Return the next payment due date after the cycle closes.

    Payment falls on ``payment_day`` in the first month whose payment day is
    strictly after the cutoff (typically the month after the cutoff).
    """
    candidate = _day_in_month(cycle_end.year, cycle_end.month, payment_day)
    if candidate > cycle_end:
        return candidate
    ny, nm = _add_month(cycle_end.year, cycle_end.month)
    return _day_in_month(ny, nm, payment_day)
