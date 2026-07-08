"""Static values for the budgets module."""

from decimal import Decimal
from typing import Final

# Supabase table backing budgets.
BUDGETS_TABLE: Final[str] = "budgets"

# Default alert threshold as a percentage of the budget amount (80 = 80%).
DEFAULT_ALERT_THRESHOLD: Final[Decimal] = Decimal("80")

# Pagination defaults.
DEFAULT_PAGE: Final[int] = 1
DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 100
