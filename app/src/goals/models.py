"""Domain models for the goals module."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.types import CurrencyType, GoalPlanKind, GoalStatus, GoalType

from .constants import DEFAULT_PRIORITY


class GoalCreate(BaseModel):
    """Data required to create a financial goal.

    A goal is always born at ``current_amount == 0``: money only enters through
    dated ``goal_contributions`` (the ledger), so there is no way to create a
    goal that already holds savings with no backing contribution. To seed an
    already-saved amount, create the goal then record a contribution.
    """

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    goal_type: GoalType = GoalType.SAVINGS
    target_amount: Decimal = Field(..., gt=0, description="Target amount (positive)")
    # None = "the user's currency": the service resolves it (profile, else the app default)
    # when the goal is created, so the default is never frozen at import time.
    currency: CurrencyType | None = None
    target_date: date | None = None
    priority: int = Field(default=DEFAULT_PRIORITY, ge=1)


class Goal(BaseModel):
    """A persisted financial goal in the domain."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    description: str | None
    goal_type: GoalType
    target_amount: Decimal
    current_amount: Decimal
    currency: CurrencyType
    target_date: date | None
    monthly_contribution: Decimal | None
    status: GoalStatus
    priority: int
    created_at: datetime


class GoalContribution(BaseModel):
    """A persisted dated contribution (aporte) toward a goal.

    Progress is the cumulative sum of these up to a month-end (mirroring
    card payments), so a goal reflects per-month progress instead of a single
    running total shown identically in every month.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    goal_id: str
    user_id: str
    amount: Decimal
    contribution_date: date
    created_at: datetime


class GoalContributionView(BaseModel):
    """A goal contribution enriched with the goal's name (for display).

    Mirrors ``CardPaymentView`` so an aporte can surface among the dashboard's
    movements, exactly as a card payment does.
    """

    goal_name: str
    amount: Decimal
    contribution_date: date


class GoalProgress(BaseModel):
    """A goal evaluated against its target and timeline."""

    goal: Goal
    percentage: float = Field(..., description="Percentage of the target reached")
    remaining: Decimal
    is_completed: bool
    months_remaining: int | None
    required_monthly_contribution: Decimal | None
    on_track: bool


class GoalPlan(BaseModel):
    """A persisted savings-plan row for a goal and month (see migration 018).

    ``month`` is always the first day of the month. A ``RECURRING`` row means
    "from this month on, X per month"; an ``OVERRIDE`` row means "in this month
    exactly X" (0 = this month I don't plan). Resolution of a month's plan lives
    in ``planning.resolve_plan``.
    """

    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: str
    goal_id: str
    user_id: str
    month: date
    planned_amount: Decimal
    kind: GoalPlanKind


class GoalMonthContribution(BaseModel):
    """GROSS amounts contributed to a goal within one month.

    ``saved`` sums the positive aportes of the month and ``withdrawn`` the absolute
    value of its retiros, so a withdrawal never cancels an aporte out.
    """

    model_config = ConfigDict(frozen=True)

    goal_id: str
    month: date
    saved: Decimal
    withdrawn: Decimal


class GoalPlanStatus(BaseModel):
    """A goal's plan vs what was actually contributed in one month.

    ``planned`` is what the user planned; ``effective_planned`` caps it at what the
    goal still lacked at the start of the month (a bigger plan is accepted, but
    ``remaining`` never asks for more than the goal can take). Amounts stay in the
    goal's own currency (no conversion).
    """

    model_config = ConfigDict(frozen=True)

    goal_id: str
    goal_name: str
    currency: CurrencyType
    month: date
    planned: Decimal
    effective_planned: Decimal
    contributed_gross: Decimal
    withdrawn: Decimal
    remaining: Decimal
    percentage: float
    is_met: bool
    goal_completed: bool


class GoalMonthLine(BaseModel):
    """One goal in one month of the month-by-month history.

    ``planned`` is ``None`` when the goal had no plan that month (distinct from a
    planned ``0``). ``cumulative`` is the goal's saved amount at the month's end.
    """

    model_config = ConfigDict(frozen=True)

    goal_id: str
    goal_name: str
    currency: CurrencyType
    month: date
    planned: Decimal | None
    saved: Decimal
    withdrawn: Decimal
    cumulative: Decimal
    # ``planned`` capped at what the goal still lacked when the month began (None
    # when there is no plan), computed like ``GoalPlanStatus.effective_planned``.
    effective_planned: Decimal | None = None


class GoalFlows(BaseModel):
    """GROSS money moved to and from goals within a date range.

    ``saved`` sums the positive aportes and ``withdrawn`` the absolute value of the
    retiros, so a withdrawal never cancels an aporte out.
    """

    model_config = ConfigDict(frozen=True)

    saved: Decimal
    withdrawn: Decimal
