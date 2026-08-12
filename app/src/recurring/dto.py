"""Data Transfer Objects for the recurring-transactions API layer."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.shared.types import PaymentMethod, TransactionType

from .models import RecurringFrequency, RecurringTransaction


class RecurringResponse(BaseModel):
    """Response body for a single recurring template.

    ``amount`` (Decimal) is serialized as a string in JSON to preserve exactness.
    """

    id: str
    description: str
    amount: Decimal
    transaction_type: TransactionType
    category: str | None
    payment_method: PaymentMethod | None
    card_id: str | None
    frequency: RecurringFrequency
    day_of_month: int
    next_run_date: date
    last_run_date: date | None
    active: bool

    @classmethod
    def from_domain(cls, rec: RecurringTransaction) -> "RecurringResponse":
        return cls(
            id=rec.id,
            description=rec.description,
            amount=rec.amount,
            transaction_type=rec.transaction_type,
            category=rec.category,
            payment_method=rec.payment_method,
            card_id=rec.card_id,
            frequency=rec.frequency,
            day_of_month=rec.day_of_month,
            next_run_date=rec.next_run_date,
            last_run_date=rec.last_run_date,
            active=rec.active,
        )


class RecurringListResponse(BaseModel):
    """Response body for the list of a user's recurring templates."""

    recurring: list[RecurringResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class RecurringRunResponse(BaseModel):
    """Response body for the daily run endpoint."""

    created: int = Field(..., ge=0, description="Transactions created this run")
