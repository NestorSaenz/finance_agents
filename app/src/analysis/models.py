"""Domain models for the holistic financial analysis."""

from datetime import date
from datetime import date as Day  # the ``date`` field below shadows the type in its class
from decimal import Decimal

from pydantic import BaseModel

from app.shared.types import Category, CurrencyType, MovementKind, StatementLineKind
from app.src.transactions.models import SpendingSummary


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
    fixed: Decimal = Decimal("0")
    limit: Decimal
    percentage: float


class GoalLine(BaseModel):
    """A savings goal's progress."""

    name: str
    current: Decimal
    target: Decimal
    percentage: float
    # Plan for the period's month (None: no plan) and the GROSS amount contributed in
    # it (withdrawals don't net out). Informational: they never change ``disposable``.
    planned_monthly: Decimal | None = None
    contributed_this_period: Decimal = Decimal("0")
    currency: CurrencyType = CurrencyType.MXN


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


class PeriodSpending(BaseModel):
    """A period's consumption plus the money set aside into goals (the single source
    for the chat and the dashboard).

    ``summary`` is the CONSUMPTION summary, untouched (``total_expenses`` stays
    consumption only). ``goal_saved`` is the gross money contributed to goals that
    counts as spending: only contributions dated on/after
    ``GOALS_COUNT_AS_SPENDING_FROM`` (the flows are clipped to that day).
    ``goal_withdrawn`` is informational and uses the SAME cutoff as ``goal_saved`` (only
    retiros dated on/after it), so the two never tell an asymmetric story; money that came
    back from goals never reduces ``total_spent``.
    """

    summary: SpendingSummary
    goal_saved: Decimal = Decimal("0")
    goal_withdrawn: Decimal = Decimal("0")

    @property
    def total_spent(self) -> Decimal:
        """Consumption plus what was set aside into goals."""
        return self.summary.total_expenses + self.goal_saved

    @property
    def balance(self) -> Decimal:
        """Income minus everything spent, goal savings included."""
        return self.summary.total_income - self.total_spent


class FinancialSnapshot(BaseModel):
    """A holistic, factual picture of the user's finances for a period.

    This is the grounded data the assistant reasons over to diagnose and
    advise — it contains facts only, no recommendations.
    """

    period: str
    income_base: Decimal  # reference monthly income (0 unless the current month)
    income_registered: Decimal  # income transactions logged in the period
    total_income: Decimal  # registered income, or income_base as fallback if none
    total_expenses: Decimal  # CONSUMPTION only (goal savings are separate)
    goal_saved: Decimal = Decimal("0")  # set aside into goals (counts as spending)
    goal_withdrawn: Decimal = Decimal("0")  # came back from goals (informational)
    # Split of total_expenses by payment method. They can sum to LESS than
    # total_expenses: rows with no payment method recorded (legacy/imported)
    # belong to neither bucket, so never present them as an exhaustive split.
    credit_expenses: Decimal  # charged to a credit card
    cash_expenses: Decimal  # cash, debit or transfer
    disposable: Decimal  # total_income - (consumption + goal_saved)
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
    expenses: Decimal  # consumption + goal_saved
    balance: Decimal  # income - expenses
    goal_saved: Decimal = Decimal("0")  # the part of ``expenses`` set aside into goals


class StatementLine(BaseModel):
    """One line read from a statement/receipt, to compare with the user's records."""

    description: str
    amount: Decimal
    date: Day | None = None  # None: the document gave no date (never reconciled)
    kind: StatementLineKind
    card: str | None = None


class ReconciledLine(BaseModel):
    """A statement line found in the user's records, and the record it matched."""

    line: StatementLine
    matched_label: str
    matched_date: date


class ReconciliationResult(BaseModel):
    """Statement lines split into already-registered and still-missing."""

    matched: list[ReconciledLine] = []
    missing: list[StatementLine] = []
