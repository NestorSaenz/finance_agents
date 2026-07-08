"""Data Transfer Objects for the budgets API layer."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.shared.types import BudgetPeriod, Category, CurrencyType, normalize_category

from .constants import DEFAULT_ALERT_THRESHOLD, MAX_PAGE_SIZE
from .models import Budget, BudgetStatus


class BudgetCreateRequest(BaseModel):
    """Request body for creating a budget."""

    name: str = Field(..., min_length=1, max_length=100, examples=["Comida mensual"])
    amount: Decimal = Field(..., gt=0, examples=[300000])
    category: Category | None = Field(
        default=None, description="Category (omit for an overall budget); custom values accepted"
    )
    currency: CurrencyType = Field(default=CurrencyType.MXN)
    period_type: BudgetPeriod = Field(default=BudgetPeriod.MONTHLY)
    start_date: date = Field(..., examples=["2024-12-01"])
    alert_threshold: Decimal = Field(
        default=DEFAULT_ALERT_THRESHOLD, ge=0, le=100, examples=[80]
    )
    alert_enabled: bool = Field(default=True)

    @field_validator("category")
    @classmethod
    def _normalize_category(cls, value: str | None) -> str | None:
        return normalize_category(value) if value else None


class BudgetResponse(BaseModel):
    """Response body for a single budget."""

    id: str
    name: str
    amount: Decimal
    category: Category | None
    currency: CurrencyType
    period_type: BudgetPeriod
    start_date: date
    end_date: date | None
    alert_threshold: Decimal
    alert_enabled: bool
    is_active: bool

    @classmethod
    def from_domain(cls, budget: Budget) -> "BudgetResponse":
        return cls(
            id=budget.id,
            name=budget.name,
            amount=budget.amount,
            category=budget.category,
            currency=budget.currency,
            period_type=budget.period_type,
            start_date=budget.start_date,
            end_date=budget.end_date,
            alert_threshold=budget.alert_threshold,
            alert_enabled=budget.alert_enabled,
            is_active=budget.is_active,
        )


class BudgetStatusResponse(BaseModel):
    """Response body for a budget evaluated against spending."""

    budget: BudgetResponse
    period_start: date
    period_end: date
    spent: Decimal
    remaining: Decimal
    percentage: float
    alert_triggered: bool

    @classmethod
    def from_domain(cls, status: BudgetStatus) -> "BudgetStatusResponse":
        return cls(
            budget=BudgetResponse.from_domain(status.budget),
            period_start=status.period_start,
            period_end=status.period_end,
            spent=status.spent,
            remaining=status.remaining,
            percentage=status.percentage,
            alert_triggered=status.alert_triggered,
        )


class BudgetListResponse(BaseModel):
    """Response body for a paginated list of budgets."""

    budgets: list[BudgetResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=MAX_PAGE_SIZE)


class BudgetAlertsResponse(BaseModel):
    """Response body for active budget alerts."""

    alerts: list[BudgetStatusResponse] = Field(default_factory=list)
    count: int = Field(..., ge=0)


class BudgetStatusListResponse(BaseModel):
    """Response body listing every active budget with its spending status."""

    statuses: list[BudgetStatusResponse] = Field(default_factory=list)
    total_budgeted: Decimal = Field(..., description="Sum of all active budget limits")
    total_spent: Decimal = Field(..., description="Sum spent across those budgets")
