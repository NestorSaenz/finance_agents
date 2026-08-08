"""Domain models for the credit-cards module."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CreditCardCreate(BaseModel):
    """Data required to register a credit card.

    Identified only by a human name (e.g. the bank) — no card numbers or any
    sensitive data are stored. ``cutoff_day``/``payment_day`` are days of the
    month (1-31) used to compute the billing cycle and next payment date.
    """

    name: str = Field(..., min_length=1, max_length=60, examples=["Visa BBVA"])
    credit_limit: Decimal = Field(..., gt=0, examples=[5000000])
    cutoff_day: int = Field(..., ge=1, le=31, description="Statement cutoff day")
    payment_day: int = Field(..., ge=1, le=31, description="Payment due day")


class CreditCard(BaseModel):
    """A persisted credit card in the domain."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    credit_limit: Decimal
    cutoff_day: int
    payment_day: int
    is_active: bool = True
    created_at: datetime


class CardPaymentCreate(BaseModel):
    """A payment made toward a credit card (reduces the balance owed)."""

    amount: Decimal = Field(..., gt=0, examples=[500000])
    payment_date: date


class CardPayment(BaseModel):
    """A persisted payment toward a credit card."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    card_id: str
    amount: Decimal
    payment_date: date
    created_at: datetime


class CardPaymentView(BaseModel):
    """A card payment enriched with the card's name (for display)."""

    card_name: str
    amount: Decimal
    payment_date: date


class CreditCardStatus(BaseModel):
    """A credit card evaluated against charges, payments and its cycle."""

    # When evaluated for a selected month (dashboard), every figure is the
    # HISTORICAL state at that month-end; with no month, it's the live state today.
    card: CreditCard
    cycle_start: date
    cycle_end: date
    spent_cycle: Decimal  # charges in the selected month, or the current cycle
    balance: Decimal  # amount owed = charges - payments (up to the eval date)
    available: Decimal  # credit_limit - max(balance, 0)
    utilization: float  # percentage of the limit used by the balance (0-100)
    next_payment_date: date
