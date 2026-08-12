"""Timezone-aware 'today' for the recurring-transactions module.

Recurring schedules are day-of-month based, so the notion of "today" must be the
user's local calendar day, not UTC. A LatAm user's "day 30" charge should fire on
their day 30 — evaluating in UTC would fire it a day early (or late) near midnight.
Both the create path (first ``next_run_date``) and the daily run endpoint compute
their reference day through this single helper so they never disagree.
"""

from datetime import UTC, date, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def recurring_today() -> date:
    """Return the current calendar day in the configured recurring timezone.

    Falls back to UTC (with a warning) if ``RECURRING_TIMEZONE`` is misconfigured,
    so an operator typo can never crash the daily run that materializes money.
    """
    tz: tzinfo
    try:
        tz = ZoneInfo(settings.RECURRING_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError) as e:
        logger.warning(
            "Invalid RECURRING_TIMEZONE; falling back to UTC",
            configured=settings.RECURRING_TIMEZONE,
            error=str(e),
        )
        tz = UTC
    return datetime.now(tz).date()
