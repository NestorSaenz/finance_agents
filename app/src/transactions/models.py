"""Domain models for the transactions module."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

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
    category: Category | None = None
    payment_method: PaymentMethod | None = None
    card_id: str | None = None  # credit card this charge belongs to (if any)
    currency: CurrencyType = CurrencyType.MXN
    source: str = DEFAULT_SOURCE


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
    source: str
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
