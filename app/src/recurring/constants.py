"""Static values for the recurring-transactions module."""

from typing import Final

# Supabase table backing recurring transaction templates.
RECURRING_TABLE: Final[str] = "recurring_transactions"

# Cap on how many past occurrences a single ``run_due`` will materialize per
# template. Bounds catch-up so a long downtime (or a badly-past next_run_date)
# can't create hundreds of rows in one pass.
MAX_CATCHUP_RUNS: Final[int] = 24

# Page size for the system-wide ``list_due`` scan. The daily run pages through all
# active templates (of every user) instead of relying on one unbounded fetch.
DUE_PAGE_SIZE: Final[int] = 500
