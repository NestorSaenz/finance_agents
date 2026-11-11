"""Data Transfer Objects for the goals API layer."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.shared.types import CurrencyType, GoalPlanScope, GoalStatus, GoalType

from .constants import DEFAULT_PRIORITY, MAX_PAGE_SIZE, MAX_PLANNED_AMOUNT
from .models import Goal, GoalContributionView, GoalMonthLine, GoalPlanStatus, GoalProgress
from .planning import month_key


class GoalCreateRequest(BaseModel):
    """Request body for creating a goal."""

    name: str = Field(..., min_length=1, max_length=100, examples=["Viaje a Japón"])
    description: str | None = Field(default=None, max_length=500)
    goal_type: GoalType = Field(default=GoalType.SAVINGS)
    target_amount: Decimal = Field(..., gt=0, examples=[100000])
    currency: CurrencyType | None = Field(
        default=None, description="Defaults to the user's profile currency (else the app default)"
    )
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


class GoalContributionItem(BaseModel):
    """Response body for a single goal contribution (as a dashboard event)."""

    goal_name: str
    amount: Decimal
    contribution_date: date

    @classmethod
    def from_domain(cls, contribution: GoalContributionView) -> "GoalContributionItem":
        return cls(
            goal_name=contribution.goal_name,
            amount=contribution.amount,
            contribution_date=contribution.contribution_date,
        )


class GoalContributionsResponse(BaseModel):
    """Response body listing goal contributions in a period."""

    contributions: list[GoalContributionItem] = Field(default_factory=list)
    total: Decimal


class GoalListResponse(BaseModel):
    """Response body for a paginated list of goals."""

    goals: list[GoalResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=MAX_PAGE_SIZE)
    total_contributed: Decimal = Field(
        default=Decimal("0"),
        description=(
            "Net contributed to goals within the requested period (0 when no period). "
            "Can be NEGATIVE when withdrawals outweigh contributions in the period."
        ),
    )


class GoalPlanRequest(BaseModel):
    """Request body for planning a goal's monthly saving."""

    amount: Decimal = Field(
        ...,
        ge=0,
        le=MAX_PLANNED_AMOUNT,
        description="Planned amount for the month (0 = don't plan).",
        examples=[500000],
    )
    scope: GoalPlanScope = Field(
        ...,
        description="'solo_mes' = only this month; 'desde_mes' = from this month on.",
    )


class GoalPlanResponse(BaseModel):
    """A goal's plan for a month after a change (``None`` = the goal has no plan then)."""

    goal_id: str
    month: str = Field(..., description="Month as YYYY-MM", examples=["2026-06"])
    planned_amount: Decimal | None


class GoalPlanStatusResponse(BaseModel):
    """A goal's plan vs contributed for one month."""

    goal_id: str
    goal_name: str
    currency: CurrencyType
    month: str
    planned: Decimal
    effective_planned: Decimal
    contributed_gross: Decimal
    withdrawn: Decimal
    remaining: Decimal
    percentage: float
    is_met: bool
    goal_completed: bool

    @classmethod
    def from_domain(cls, status: GoalPlanStatus) -> "GoalPlanStatusResponse":
        return cls(
            goal_id=status.goal_id,
            goal_name=status.goal_name,
            currency=status.currency,
            month=month_key(status.month),
            planned=status.planned,
            effective_planned=status.effective_planned,
            contributed_gross=status.contributed_gross,
            withdrawn=status.withdrawn,
            remaining=status.remaining,
            percentage=status.percentage,
            is_met=status.is_met,
            goal_completed=status.goal_completed,
        )


class GoalPlanStatusListResponse(BaseModel):
    """Plan status of every planned goal for a month, with totals PER CURRENCY.

    Totals never mix currencies: each map is keyed by the goals' own currency.
    """

    statuses: list[GoalPlanStatusResponse] = Field(default_factory=list)
    total_planned: dict[CurrencyType, Decimal] = Field(default_factory=dict)
    total_effective_planned: dict[CurrencyType, Decimal] = Field(
        default_factory=dict,
        description="Sum of the plans capped at what each goal still lacked (use for 'faltan').",
    )
    total_saved: dict[CurrencyType, Decimal] = Field(default_factory=dict)
    total_withdrawn: dict[CurrencyType, Decimal] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, statuses: Sequence[GoalPlanStatus]) -> "GoalPlanStatusListResponse":
        planned: dict[CurrencyType, Decimal] = defaultdict(lambda: Decimal("0"))
        effective: dict[CurrencyType, Decimal] = defaultdict(lambda: Decimal("0"))
        saved: dict[CurrencyType, Decimal] = defaultdict(lambda: Decimal("0"))
        withdrawn: dict[CurrencyType, Decimal] = defaultdict(lambda: Decimal("0"))
        for s in statuses:
            planned[s.currency] += s.planned
            effective[s.currency] += s.effective_planned
            saved[s.currency] += s.contributed_gross
            withdrawn[s.currency] += s.withdrawn
        return cls(
            statuses=[GoalPlanStatusResponse.from_domain(s) for s in statuses],
            total_planned=dict(planned),
            total_effective_planned=dict(effective),
            total_saved=dict(saved),
            total_withdrawn=dict(withdrawn),
        )


class GoalMonthLineResponse(BaseModel):
    """One goal in one month of the history."""

    goal_id: str
    goal_name: str
    currency: CurrencyType
    month: str
    planned: Decimal | None
    effective_planned: Decimal | None = Field(
        default=None,
        description="Plan capped at what the goal still lacked at the month start (null: no plan)",
    )
    saved: Decimal
    withdrawn: Decimal
    cumulative: Decimal

    @classmethod
    def from_domain(cls, line: GoalMonthLine) -> "GoalMonthLineResponse":
        return cls(
            goal_id=line.goal_id,
            goal_name=line.goal_name,
            currency=line.currency,
            month=month_key(line.month),
            planned=line.planned,
            effective_planned=line.effective_planned,
            saved=line.saved,
            withdrawn=line.withdrawn,
            cumulative=line.cumulative,
        )


class GoalMonthlyHistoryResponse(BaseModel):
    """Month-by-month plan vs contributed, ordered by goal then month."""

    lines: list[GoalMonthLineResponse] = Field(default_factory=list)

    @classmethod
    def from_domain(cls, lines: Sequence[GoalMonthLine]) -> "GoalMonthlyHistoryResponse":
        return cls(lines=[GoalMonthLineResponse.from_domain(line) for line in lines])
