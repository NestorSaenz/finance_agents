"""Static values for the analysis module."""

from typing import Final

# Bounds for the month-over-month trend. A trend needs at least two points to
# BE a trend; the upper bound caps the fan-out (one aggregation per month) and
# keeps the tool result small enough for the LLM to narrate.
MIN_TREND_MONTHS: Final[int] = 2
MAX_TREND_MONTHS: Final[int] = 12
DEFAULT_TREND_MONTHS: Final[int] = 6

# A statement line matches a record whose transaction_date is within this many days
# (banks post a purchase a day or two after it was made; users log it when they remember).
RECONCILE_WINDOW_DAYS: Final[int] = 3
