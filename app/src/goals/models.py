"""Domain models for the goals module."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.types import CurrencyType, GoalStatus, GoalType

from .constants import DEFAULT_PRIORITY


class GoalCreate(BaseModel):
    """Data required to create a financial goal."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    goal_type: GoalType = GoalType.SAVINGS
    target_amount: Decimal = Field(..., gt=0, description="Target amount (positive)")
    current_amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: CurrencyType = CurrencyType.MXN
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
