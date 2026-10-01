"""Domain models for the holistic financial analysis."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.shared.types import Category, MovementKind


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
    """A credit card's total debt, available credit and what's due next.

    ``balance`` is the TOTAL debt (it includes the open cycle), not the amount
    due on ``next_payment_date`` — that is ``statement_amount`` (None while the
    statement it settles is still open). ``overdue_amount`` is unpaid debt whose
    due date already passed (only set when the next date is the open cycle's).
    """

    name: str
    balance: Decimal
    limit: Decimal
    available: Decimal
    next_payment_date: date
    statement_amount: Decimal | None = None
    overdue_amount: Decimal | None = None


class MovementCandidate(BaseModel):
    """A single movement found across the transaction/card/goal ledgers.

    Unifies the three sources the dashboard's movements list shows, so the agent
    can locate a movement to delete/edit regardless of which ledger holds it and
    route to the right tool by ``kind``. ``amount`` is always the positive
    magnitude shown to the user; the sign lives in ``kind`` (a retiro vs an
    aporte). ``label`` is the human name: a transaction's description, a card's
    name, or a goal's name.
    """

    kind: MovementKind
    label: str
    amount: Decimal
    date: date


class FinancialSnapshot(BaseModel):
    """A holistic, factual picture of the user's finances for a period.

    This is the grounded data the assistant reasons over to diagnose and
    advise — it contains facts only, no recommendations.
    """

    period: str
    income_base: Decimal  # reference monthly income (0 unless the current month)
    income_registered: Decimal  # income transactions logged in the period
    total_income: Decimal  # registered income, or income_base as fallback if none
    total_expenses: Decimal
    # Split of total_expenses by payment method. They can sum to LESS than
    # total_expenses: rows with no payment method recorded (legacy/imported)
    # belong to neither bucket, so never present them as an exhaustive split.
    credit_expenses: Decimal  # charged to a credit card
    cash_expenses: Decimal  # cash, debit or transfer
    disposable: Decimal  # total_income - total_expenses
    savings_target_pct: Decimal | None
    savings_target_amount: Decimal | None  # total_income * pct
    by_category: list[CategoryLine]
    budgets: list[BudgetLine]
    goals: list[GoalLine]
    cards: list[CardLine]
    card_debt_total: Decimal
    card_available_total: Decimal


class MonthlyTotals(BaseModel):
    """Income and expenses of a single calendar month (one point of a trend)."""

    month: str  # "YYYY-MM"
    income: Decimal
    expenses: Decimal
    balance: Decimal  # income - expenses
