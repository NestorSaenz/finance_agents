"""Domain models for the holistic financial analysis."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.shared.types import Category


class CategoryLine(BaseModel):
    """Expense in a category and its share of total expenses."""

    category: Category
    amount: Decimal
    percentage: float


class BudgetLine(BaseModel):
    """A budget's spend vs its limit for the period."""

    category: Category | None
    name: str
    spent: Decimal
    limit: Decimal
    percentage: float


class GoalLine(BaseModel):
    """A savings goal's progress."""

    name: str
    current: Decimal
    target: Decimal
    percentage: float


class CardLine(BaseModel):
    """A credit card's debt and available credit."""

    name: str
    balance: Decimal
    limit: Decimal
    available: Decimal
    next_payment_date: date


class FinancialSnapshot(BaseModel):
    """A holistic, factual picture of the user's finances for a period.

    This is the grounded data the assistant reasons over to diagnose and
    advise — it contains facts only, no recommendations.
    """

    period: str
    income_base: Decimal  # reference monthly income (0 unless the current month)
    income_registered: Decimal  # income transactions logged in the period
    total_income: Decimal  # income_base + income_registered
    total_expenses: Decimal
    disposable: Decimal  # total_income - total_expenses
    savings_target_pct: Decimal | None
    savings_target_amount: Decimal | None  # total_income * pct
    by_category: list[CategoryLine]
    budgets: list[BudgetLine]
    goals: list[GoalLine]
    cards: list[CardLine]
    card_debt_total: Decimal
    card_available_total: Decimal
