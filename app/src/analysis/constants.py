"""Static values for the analysis module."""

from typing import Final

# Bounds for the month-over-month trend. A trend needs at least two points to
# BE a trend; the upper bound caps the fan-out (one aggregation per month) and
# keeps the tool result small enough for the LLM to narrate.
MIN_TREND_MONTHS: Final[int] = 2
MAX_TREND_MONTHS: Final[int] = 12
DEFAULT_TREND_MONTHS: Final[int] = 6
