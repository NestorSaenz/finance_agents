"""Domain models for the recurring-transactions module.

A recurring transaction is a TEMPLATE for a movement that repeats (a salary, a
rent, a subscription). A daily job materializes the due ones into real
transactions via the transaction service; the template only carries the schedule.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.types import Category, PaymentMethod, TransactionType


class RecurringFrequency(StrEnum):
    """How often a recurring template repeats.

    Only ``MONTHLY`` is supported for now, but it is modeled as an enum so
    weekly/yearly can be added without changing the column type.
    """

    MONTHLY = "monthly"


def _today() -> date:
    return datetime.now(UTC).date()


class RecurringCreate(BaseModel):
    """Data required to create a recurring template.

    ``next_run_date`` is computed by the service (the next occurrence of
    ``day_of_month`` on or after today), not supplied by the user; it defaults to
    today so callers never have to pass it.
    """

    amount: Decimal = Field(..., gt=0, description="Amount per occurrence (positive)")
    description: str = Field(..., min_length=1, max_length=500)
    transaction_type: TransactionType
    category: Category | None = None
    payment_method: PaymentMethod | None = None
    card_id: str | None = None  # credit card this charge belongs to (if any)
    frequency: RecurringFrequency = RecurringFrequency.MONTHLY
    day_of_month: int = Field(..., ge=1, le=31, description="Day of month (1-31)")
    next_run_date: date = Field(default_factory=_today)
    active: bool = True

    @model_validator(mode="after")
    def _income_cannot_be_credit(self) -> "RecurringCreate":
        """A credit-linked recurrente is definitionally an expense.

        Mirrors ``TransactionCreate``'s guard: without it, an income template
        tagged 'credito' (or linked to a card) materializes every occurrence as
        a transaction excluded from card/budget sums but still counted as
        income — the same silent accumulated-surplus inflation bug, recurring.
        """
        if self.transaction_type == TransactionType.INCOME and (
            self.payment_method == PaymentMethod.CREDITO or self.card_id is not None
        ):
            raise ValueError(
                "A recurring income cannot use the 'credito' payment method or "
                "be linked to a credit card"
            )
        return self


class RecurringUpdate(BaseModel):
    """Mutable fields of a recurring template (all optional)."""

    amount: Decimal | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    transaction_type: TransactionType | None = None
    category: Category | None = None
    payment_method: PaymentMethod | None = None
    card_id: str | None = None
    # Explicitly unlink the card (set card_id to NULL) without switching to cash.
    # Distinct from ``card_id is None`` which just means "leave the link unchanged".
    clear_card: bool = False
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    active: bool | None = None


class RecurringTransaction(BaseModel):
    """A persisted recurring template in the domain."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    amount: Decimal
    description: str
    transaction_type: TransactionType
    category: Category | None
    payment_method: PaymentMethod | None
    card_id: str | None
    frequency: RecurringFrequency
    day_of_month: int
    next_run_date: date
    last_run_date: date | None
    active: bool
    created_at: datetime
