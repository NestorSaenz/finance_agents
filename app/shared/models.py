"""Shared domain models for FinanceGPT.

This module defines Pydantic models for core domain entities
that are used across multiple modules.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.shared.types import (
    Amount,
    BudgetId,
    BudgetPeriod,
    CategoryId,
    CurrencyType,
    GoalId,
    GoalStatus,
    GoalType,
    TransactionId,
    TransactionType,
    UserId,
)

# =============================================================================
# Transaction Models
# =============================================================================


class TransactionBase(BaseModel):
    """Base fields for a transaction."""

    amount: Amount = Field(..., gt=0, description="Transaction amount")
    currency: CurrencyType = Field(
        default=CurrencyType.MXN, description="Currency code"
    )
    description: str = Field(
        ..., min_length=1, max_length=500, description="Transaction description"
    )
    transaction_type: TransactionType = Field(..., description="Income or expense")
    transaction_date: date = Field(..., description="Date of the transaction")


class TransactionCreate(TransactionBase):
    """Model for creating a new transaction."""

    category: str | None = Field(
        default=None, description="Category (auto-detected if not provided)"
    )
    tags: list[str] = Field(default_factory=list, description="User-defined tags")
    notes: str | None = Field(default=None, max_length=1000, description="Notes")
    is_recurring: bool = Field(default=False, description="Is recurring transaction")


class Transaction(TransactionBase):
    """Complete transaction model with all fields."""

    id: TransactionId = Field(..., description="Unique transaction identifier")
    user_id: UserId = Field(..., description="Owner user ID")
    category: str = Field(..., description="Transaction category")
    category_id: CategoryId | None = Field(
        default=None, description="Reference to categories table"
    )
    ai_category_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="AI categorization confidence"
    )
    ai_insights: str | None = Field(
        default=None, description="AI-generated insights about transaction"
    )
    tags: list[str] = Field(default_factory=list, description="User-defined tags")
    notes: str | None = Field(default=None, description="Additional notes")
    is_recurring: bool = Field(default=False, description="Is recurring transaction")
    source: str = Field(default="manual", description="Transaction source")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


# =============================================================================
# Category Models
# =============================================================================


class Category(BaseModel):
    """Category model for transactions."""

    id: CategoryId = Field(..., description="Unique category identifier")
    user_id: UserId | None = Field(
        default=None, description="Owner user ID (null for system categories)"
    )
    name: str = Field(..., min_length=1, max_length=100, description="Category name")
    type: TransactionType = Field(..., description="Income or expense category")
    icon: str | None = Field(default=None, description="Emoji or icon name")
    color: str | None = Field(default=None, description="Hex color code")
    is_system: bool = Field(default=False, description="System vs user-created")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True


# =============================================================================
# Budget Models
# =============================================================================


class BudgetBase(BaseModel):
    """Base fields for a budget."""

    name: str = Field(..., min_length=1, max_length=200, description="Budget name")
    amount: Amount = Field(..., gt=0, description="Budget amount")
    currency: CurrencyType = Field(default=CurrencyType.MXN, description="Currency")
    period_type: BudgetPeriod = Field(
        default=BudgetPeriod.MONTHLY, description="Budget period"
    )
    alert_threshold: Decimal = Field(
        default=Decimal("80"), ge=0, le=100, description="Alert at % spent"
    )
    alert_enabled: bool = Field(default=True, description="Enable alerts")


class BudgetCreate(BudgetBase):
    """Model for creating a new budget."""

    category_id: CategoryId | None = Field(
        default=None, description="Category to budget"
    )
    start_date: date = Field(..., description="Budget start date")
    end_date: date | None = Field(default=None, description="Budget end date")


class Budget(BudgetBase):
    """Complete budget model."""

    id: BudgetId = Field(..., description="Unique budget identifier")
    user_id: UserId = Field(..., description="Owner user ID")
    category_id: CategoryId | None = Field(default=None, description="Budgeted category")
    start_date: date = Field(..., description="Budget start date")
    end_date: date | None = Field(default=None, description="Budget end date")
    is_active: bool = Field(default=True, description="Budget is active")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True


# =============================================================================
# Goal Models
# =============================================================================


class GoalBase(BaseModel):
    """Base fields for a financial goal."""

    name: str = Field(..., min_length=1, max_length=200, description="Goal name")
    description: str | None = Field(
        default=None, max_length=1000, description="Goal description"
    )
    type: GoalType = Field(..., description="Type of financial goal")
    target_amount: Amount = Field(..., gt=0, description="Target amount to reach")
    currency: CurrencyType = Field(default=CurrencyType.MXN, description="Currency")
    target_date: date | None = Field(default=None, description="Target completion date")


class GoalCreate(GoalBase):
    """Model for creating a new goal."""

    current_amount: Amount = Field(
        default=Decimal("0"), ge=0, description="Current progress"
    )
    priority: int = Field(default=1, ge=1, le=5, description="Priority level")


class Goal(GoalBase):
    """Complete goal model."""

    id: GoalId = Field(..., description="Unique goal identifier")
    user_id: UserId = Field(..., description="Owner user ID")
    current_amount: Amount = Field(default=Decimal("0"), description="Current progress")
    monthly_contribution: Amount | None = Field(
        default=None, description="Suggested monthly contribution"
    )
    status: GoalStatus = Field(default=GoalStatus.ACTIVE, description="Goal status")
    priority: int = Field(default=1, ge=1, le=5, description="Priority level")
    ai_strategy: str | None = Field(
        default=None, description="AI-generated saving strategy"
    )
    ai_progress_analysis: str | None = Field(
        default=None, description="AI progress analysis"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True

    @property
    def progress_percentage(self) -> float:
        """Calculate progress towards goal as percentage."""
        if self.target_amount <= 0:
            return 0.0
        return float(self.current_amount / self.target_amount * 100)

    @property
    def remaining_amount(self) -> Decimal:
        """Calculate remaining amount to reach goal."""
        remaining = self.target_amount - self.current_amount
        return max(Decimal("0"), remaining)


# =============================================================================
# User Profile Models
# =============================================================================


class UserProfile(BaseModel):
    """User financial profile."""

    id: str = Field(..., description="Profile identifier")
    user_id: UserId = Field(..., description="Owner user ID")
    monthly_income: Amount | None = Field(default=None, description="Monthly income")
    income_currency: CurrencyType = Field(
        default=CurrencyType.MXN, description="Income currency"
    )
    savings_goal_percentage: Decimal = Field(
        default=Decimal("20"), ge=0, le=100, description="Savings goal %"
    )
    emergency_fund_months: int = Field(
        default=6, ge=1, le=24, description="Emergency fund target months"
    )
    preferred_language: str = Field(default="es", description="Preferred language")
    onboarding_completed: bool = Field(
        default=False, description="Onboarding completed"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    class Config:
        from_attributes = True
