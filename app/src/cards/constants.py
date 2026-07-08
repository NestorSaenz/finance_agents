"""Static values for the credit-cards module."""

from typing import Final

# Supabase table backing the user's credit cards.
CREDIT_CARDS_TABLE: Final[str] = "credit_cards"

# How many transactions the cycle-spend fallback fetches to aggregate.
CYCLE_FETCH_LIMIT: Final[int] = 1000
