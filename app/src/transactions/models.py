"""Domain models for the transactions module."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.types import Category, CurrencyType, PaymentMethod, TransactionType

from .constants import DEFAULT_SOURCE


class TransactionCreate(BaseModel):
    """Data required to create a transaction.

    ``category`` is optional: when omitted the service auto-categorizes the
    transaction from its description using semantic similarity. ``payment_method``
    is optional too (unknown until the user states cash vs credit).
    """

    amount: Decimal = Field(..., gt=0, description="Transaction amount (positive)")
    description: str = Field(..., min_length=1, max_length=500)
    transaction_type: TransactionType
    transaction_date: date
    # Month a credit charge actually hits the budget (its statement's payment
    # date). None -> the repository defaults it to transaction_date (cash/debit).
    budget_date: date | None = None
    category: Category | None = None
    payment_method: PaymentMethod | None = None
    card_id: str | None = None  # credit card this charge belongs to (if any)
    currency: CurrencyType = CurrencyType.MXN
    source: str = DEFAULT_SOURCE
    # Provenance of a materialized recurring occurrence. Both stay None on the
    # normal create path; set together they key the DB unique index that makes
    # materialization exactly-once (see TransactionService.materialize_occurrence).
    recurring_id: str | None = None
    occurrence_date: date | None = None

    @model_validator(mode="after")
    def _income_cannot_be_credit(self) -> "TransactionCreate":
        """A credit charge is definitionally an expense — never an income.

        Without this guard an income mistakenly tagged 'credito'/linked to a
        card gets excluded from card and budget sums (both filter type='expense')
        while still counting toward income, silently inflating figures like the
        accumulated surplus. Enforced here so every caller (register, update,
        installments, recurring materialization) is covered, not just the tool.
        """
        if self.transaction_type == TransactionType.INCOME and (
            self.payment_method == PaymentMethod.CREDITO or self.card_id is not None
        ):
            raise ValueError(
                "An income cannot use the 'credito' payment method or be "
                "linked to a credit card"
            )
        return self


class Transaction(BaseModel):
    """A persisted transaction in the domain."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    amount: Decimal
    currency: CurrencyType
    transaction_type: TransactionType
    description: str
    category: Category
    payment_method: PaymentMethod | None = None
    card_id: str | None = None
    transaction_date: date
    # Budget attribution date (= transaction_date for cash; the credit statement's
    # payment date for credit). Drives which month's budget the charge affects.
    budget_date: date
    source: str
    # Set only on a materialized recurring occurrence; excluded from budget sums
    # (migration 014) since a budget watches variable spending, not fixed bills.
    recurring_id: str | None = None
    created_at: datetime


class CategorySpending(BaseModel):
    """Total expense for a single category in a period."""

    category: Category
    amount: Decimal


class SpendingSummary(BaseModel):
    """Aggregated income/expenses for a period (powers the dashboard)."""

    total_income: Decimal
    total_expenses: Decimal
    by_category: list[CategorySpending]  # expenses only, highest first
    credit_expenses: Decimal = Decimal("0")  # paid with a credit card
    cash_expenses: Decimal = Decimal("0")  # cash, debit or transfer
