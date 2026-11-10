"""Static values for the goals module."""

from decimal import Decimal
from typing import Final

# Supabase table backing goals.
GOALS_TABLE: Final[str] = "goals"

# Default priority (1 = highest).
DEFAULT_PRIORITY: Final[int] = 1

# Pagination defaults.
DEFAULT_PAGE: Final[int] = 1
DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 100

# Supabase table holding the monthly savings plans of goals (migration 018).
GOAL_PLANS_TABLE: Final[str] = "goal_plans"
# Unique key of goal_plans: one row per (goal, month, kind); the upsert target.
GOAL_PLANS_CONFLICT: Final[str] = "goal_id,month,kind"
# Postgres function returning gross saved/withdrawn per (goal, month) (migration 018).
GOAL_MONTHLY_CONTRIBUTIONS_RPC: Final[str] = "goal_monthly_contributions"

# goal_plans.planned_amount is NUMERIC(12, 2): the largest storable plan.
MAX_PLANNED_AMOUNT: Final[Decimal] = Decimal("9999999999.99")
# Plans are stored in cents.
PLAN_AMOUNT_QUANTUM: Final[Decimal] = Decimal("0.01")

# Month-by-month history: default window (months before the chosen month) and cap.
DEFAULT_HISTORY_MONTHS: Final[int] = 6
MAX_HISTORY_MONTHS: Final[int] = 24
