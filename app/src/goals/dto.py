"""Data Transfer Objects for the goals API layer."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.shared.types import CurrencyType, GoalStatus, GoalType

from .constants import DEFAULT_PRIORITY, MAX_PAGE_SIZE
from .models import Goal, GoalProgress


class GoalCreateRequest(BaseModel):
    """Request body for creating a goal."""

    name: str = Field(..., min_length=1, max_length=100, examples=["Viaje a Japón"])
    description: str | None = Field(default=None, max_length=500)
    goal_type: GoalType = Field(default=GoalType.SAVINGS)
    target_amount: Decimal = Field(..., gt=0, examples=[100000])
    current_amount: Decimal = Field(default=Decimal("0"), ge=0, examples=[25000])
    currency: CurrencyType = Field(default=CurrencyType.MXN)
    target_date: date | None = Field(default=None, examples=["2025-12-31"])
    priority: int = Field(default=DEFAULT_PRIORITY, ge=1)


class GoalUpdateRequest(BaseModel):
    """Request body for updating a goal's editable fields (all optional)."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    target_amount: Decimal | None = Field(default=None, gt=0, examples=[15000000])
    target_date: date | None = Field(default=None, examples=["2026-12-31"])


class GoalContributeRequest(BaseModel):
    """Request body for contributing to a goal."""

    amount: Decimal = Field(..., gt=0, description="Amount to add", examples=[5000])
    contribution_date: date | None = Field(
        default=None,
        description="Date of the contribution (YYYY-MM-DD); defaults to today.",
        examples=["2026-06-15"],
    )


class GoalResponse(BaseModel):
    """Response body for a single goal."""

    id: str
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

    @classmethod
    def from_domain(cls, goal: Goal) -> "GoalResponse":
        return cls(
            id=goal.id,
            name=goal.name,
            description=goal.description,
            goal_type=goal.goal_type,
            target_amount=goal.target_amount,
            current_amount=goal.current_amount,
            currency=goal.currency,
            target_date=goal.target_date,
            monthly_contribution=goal.monthly_contribution,
            status=goal.status,
            priority=goal.priority,
        )


class GoalProgressResponse(BaseModel):
    """Response body for a goal's progress."""

    goal: GoalResponse
    percentage: float
    remaining: Decimal
    is_completed: bool
    months_remaining: int | None
    required_monthly_contribution: Decimal | None
    on_track: bool

    @classmethod
    def from_domain(cls, progress: GoalProgress) -> "GoalProgressResponse":
        return cls(
            goal=GoalResponse.from_domain(progress.goal),
            percentage=progress.percentage,
            remaining=progress.remaining,
            is_completed=progress.is_completed,
            months_remaining=progress.months_remaining,
            required_monthly_contribution=progress.required_monthly_contribution,
            on_track=progress.on_track,
        )


class GoalListResponse(BaseModel):
    """Response body for a paginated list of goals."""

    goals: list[GoalResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=MAX_PAGE_SIZE)
    total_contributed: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="Total contributed to goals within the requested period (0 when no period).",
    )
