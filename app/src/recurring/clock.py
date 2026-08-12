"""Timezone-aware 'today' for the recurring-transactions module.

Recurring schedules are day-of-month based, so the notion of "today" must be the
user's local calendar day, not UTC. A LatAm user's "day 30" charge should fire on
their day 30 — evaluating in UTC would fire it a day early (or late) near midnight.
Both the create path (first ``next_run_date``) and the daily run endpoint compute
their reference day through this single helper so they never disagree.
"""

from datetime import date

from app.core.config import settings
from app.shared.clock import local_today


def recurring_today() -> date:
    """Return the current calendar day in the configured recurring timezone.

    Falls back to UTC (with a warning) if ``RECURRING_TIMEZONE`` is misconfigured,
    so an operator typo can never crash the daily run that materializes money.
    Delegates to the shared ``local_today`` helper so the app has one timezone
    clock; the name/signature are kept to avoid churn in recurring call sites.
    """
    return local_today(settings.RECURRING_TIMEZONE)
