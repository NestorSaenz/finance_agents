"""Pure helpers for goal savings plans (no I/O): month math and plan resolution."""

import calendar
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from app.shared.clock import local_date
from app.shared.types import GoalPlanKind

from .models import GoalPlan


def first_of_month(day: date) -> date:
    """Return the first day of the month containing ``day``."""
    return day.replace(day=1)


def last_of_month(day: date) -> date:
    """Return the last day of the month containing ``day``."""
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def add_months(month: date, count: int) -> date:
    """Return the first day of the month ``count`` months after ``month`` (may be negative)."""
    index = month.year * 12 + (month.month - 1) + count
    return date(index // 12, index % 12 + 1, 1)


def goal_created_month(created_at: datetime, tz: str | None) -> date:
    """Return the first day of the month, on the ``tz`` calendar, in which a goal was created.

    ``created_at`` is a UTC instant; near a month boundary the local month differs
    (23:30 on Oct 31 in Bogota is already Nov 1 in UTC).
    """
    return first_of_month(local_date(created_at, tz))


def month_range(start: date, end: date) -> list[date]:
    """Return the first day of every month from ``start``'s to ``end``'s, inclusive."""
    first, last = first_of_month(start), first_of_month(end)
    span = (last.year - first.year) * 12 + (last.month - first.month)
    return [add_months(first, offset) for offset in range(span + 1)]


def month_key(month: date) -> str:
    """Format a month as ``YYYY-MM`` (the API's month format)."""
    return month.isoformat()[:7]


def resolve_plan(
    plans: Sequence[GoalPlan], month: date, goal_created_month: date
) -> Decimal | None:
    """Return what a goal plans to save in ``month``, or ``None`` when it has no plan.

    ``plans`` are the goal's own rows. Resolution order:

    1. An ``OVERRIDE`` for the month wins, even when it is 0 ("this month I don't plan").
    2. Otherwise the latest ``RECURRING`` starting on or before the month applies
       (a recurring of 0 means "stop planning from that month on").
    3. Otherwise there is no plan (``None``, which is NOT the same as a planned 0).

    A goal has no plan in any month before the one it was created in.
    """
    target = month.replace(day=1)
    if target < goal_created_month.replace(day=1):
        return None

    override = next(
        (p for p in plans if p.kind == GoalPlanKind.OVERRIDE and p.month == target), None
    )
    if override is not None:
        return override.planned_amount

    latest_recurring = max(
        (p for p in plans if p.kind == GoalPlanKind.RECURRING and p.month <= target),
        key=lambda p: p.month,
        default=None,
    )
    return latest_recurring.planned_amount if latest_recurring is not None else None
