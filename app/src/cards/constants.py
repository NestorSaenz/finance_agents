"""Static values for the credit-cards module."""

from typing import Final

# Supabase table backing the user's credit cards.
CREDIT_CARDS_TABLE: Final[str] = "credit_cards"

# How many transactions the cycle-spend fallback fetches to aggregate.
CYCLE_FETCH_LIMIT: Final[int] = 1000

# How many of a card's transactions the budget-date re-sync fetches to re-date.
BUDGET_SYNC_FETCH_LIMIT: Final[int] = 1000

# Max concurrent row updates while re-dating, so a big card can't open a connection storm.
BUDGET_SYNC_CONCURRENCY: Final[int] = 8
