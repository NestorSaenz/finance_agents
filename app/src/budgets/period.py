"""Period computation for budgets."""

import calendar
from datetime import date, timedelta

from app.shared.types import BudgetPeriod


def compute_period(period_type: BudgetPeriod, reference: date) -> tuple[date, date]:
    """Return the (start, end) dates of the period containing ``reference``.

    Args:
        period_type: weekly, monthly, or yearly.
        reference: A date within the desired period (typically today).

    Returns:
        Inclusive (start_date, end_date) of the period.
    """
    if period_type == BudgetPeriod.WEEKLY:
        start = reference - timedelta(days=reference.weekday())  # Monday
        return start, start + timedelta(days=6)

    if period_type == BudgetPeriod.YEARLY:
        return date(reference.year, 1, 1), date(reference.year, 12, 31)

    # Monthly (default).
    last_day = calendar.monthrange(reference.year, reference.month)[1]
    return (
        date(reference.year, reference.month, 1),
        date(reference.year, reference.month, last_day),
    )
