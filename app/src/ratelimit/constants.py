"""Static values for the rate-limiting module."""

from typing import Final

# Supabase function backing the per-user counters (migration 012). The table
# (`rate_limits`) is only ever touched inside the function, so it needs no constant.
CHECK_RATE_LIMIT_RPC: Final[str] = "check_rate_limit"
