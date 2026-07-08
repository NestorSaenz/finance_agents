"""Static values for the goals module."""

from typing import Final

# Supabase table backing goals.
GOALS_TABLE: Final[str] = "goals"

# Default priority (1 = highest).
DEFAULT_PRIORITY: Final[int] = 1

# Pagination defaults.
DEFAULT_PAGE: Final[int] = 1
DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 100
