"""Static values for the transactions module."""

from typing import Final

# Supabase table backing transactions.
TRANSACTIONS_TABLE: Final[str] = "transactions"

# Pinecone namespace holding the indexed category examples used for
# semantic auto-categorization.
CATEGORIES_NAMESPACE: Final[str] = "categories"

# Default source for transactions created through the API.
DEFAULT_SOURCE: Final[str] = "manual"

# Pagination defaults.
DEFAULT_PAGE: Final[int] = 1
DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 100

# How many transactions the spending summary fetches to aggregate in-period.
SUMMARY_FETCH_LIMIT: Final[int] = 1000

# Minimum cosine similarity required to trust a semantic category match.
# Below this the transaction is categorized as OTROS (unknown).
CATEGORY_CONFIDENCE_THRESHOLD: Final[float] = 0.50
