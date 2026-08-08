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

# Minimum string similarity to snap a proposed category onto one the user already
# uses (typo tolerance, e.g. "improvistos" -> existing "imprevistos"). High cutoff
# so genuinely different categories ("ahorro" vs "ahorro carro") are NOT merged.
CATEGORY_FUZZY_MATCH_CUTOFF: Final[float] = 0.85

# Upper bound for a deferred purchase split into monthly installments (cuotas),
# so a typo can't spawn hundreds of transactions. 72 = 6 years, the longest plan
# banks realistically offer here.
MAX_INSTALLMENTS: Final[int] = 72
