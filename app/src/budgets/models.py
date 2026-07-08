"""Domain models for the budgets module."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.types import BudgetPeriod, Category, CurrencyType

from .constants import DEFAULT_ALERT_THRESHOLD


class BudgetCreate(BaseModel):
    """Data required to create a budget.

    A ``None`` category means an overall budget across all categories.
    ``alert_threshold`` is a percentage of ``amount`` (e.g. 80 = alert at 80%).
    """

    name: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., gt=0, description="Budget limit (positive)")
    category: Category | None = None
    currency: CurrencyType = CurrencyType.MXN
    period_type: BudgetPeriod = BudgetPeriod.MONTHLY
    start_date: date
    alert_threshold: Decimal = Field(
        default=DEFAULT_ALERT_THRESHOLD, ge=0, le=100, description="Alert percentage"
    )
    alert_enabled: bool = True


class Budget(BaseModel):
    """A persisted budget in the domain."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
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
    created_at: datetime


class BudgetStatus(BaseModel):
    """A budget evaluated against actual spending in the current period."""

    budget: Budget
    period_start: date
    period_end: date
    spent: Decimal
    remaining: Decimal
    percentage: float = Field(..., description="Percentage of the budget spent")
    alert_triggered: bool
