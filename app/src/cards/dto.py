"""Data Transfer Objects for the credit-cards API layer."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from .models import CardPaymentView, CreditCard, CreditCardStatus


class CreditCardCreateRequest(BaseModel):
    """Request body for registering a credit card (no sensitive data)."""

    name: str = Field(..., min_length=1, max_length=60, examples=["Visa BBVA"])
    credit_limit: Decimal = Field(..., gt=0, examples=[5000000])
    cutoff_day: int = Field(..., ge=1, le=31, examples=[15])
    payment_day: int = Field(..., ge=1, le=31, examples=[5])


class CardPaymentRequest(BaseModel):
    """Request body for registering a payment toward a card."""

    amount: Decimal = Field(..., gt=0, examples=[500000])
    payment_date: date | None = Field(default=None, description="Defaults to today")


class CreditCardResponse(BaseModel):
    """Response body for a single credit card."""

    id: str
    name: str
    credit_limit: Decimal
    cutoff_day: int
    payment_day: int

    @classmethod
    def from_domain(cls, card: CreditCard) -> "CreditCardResponse":
        return cls(
            id=card.id,
            name=card.name,
            credit_limit=card.credit_limit,
            cutoff_day=card.cutoff_day,
            payment_day=card.payment_day,
        )


class CreditCardStatusResponse(BaseModel):
    """Response body for a card evaluated against its cycle and balance."""

    card: CreditCardResponse
    cycle_start: date
    cycle_end: date
    spent_cycle: Decimal
    balance: Decimal
    available: Decimal
    utilization: float
    next_payment_date: date

    @classmethod
    def from_domain(cls, status: CreditCardStatus) -> "CreditCardStatusResponse":
        return cls(
            card=CreditCardResponse.from_domain(status.card),
            cycle_start=status.cycle_start,
            cycle_end=status.cycle_end,
            spent_cycle=status.spent_cycle,
            balance=status.balance,
            available=status.available,
            utilization=status.utilization,
            next_payment_date=status.next_payment_date,
        )


class CreditCardStatusListResponse(BaseModel):
    """Response body listing every card with its status (dashboard)."""

    cards: list[CreditCardStatusResponse] = Field(default_factory=list)
    total_limit: Decimal
    total_balance: Decimal
    total_available: Decimal


class CardPaymentResponse(BaseModel):
    """Response body for a single card payment (as an event)."""

    card_id: str
    card_name: str
    amount: Decimal
    payment_date: date

    @classmethod
    def from_domain(cls, payment: CardPaymentView) -> "CardPaymentResponse":
        return cls(
            card_id=payment.card_id,
            card_name=payment.card_name,
            amount=payment.amount,
            payment_date=payment.payment_date,
        )


class CardPaymentsListResponse(BaseModel):
    """Response body listing card payments in a period."""

    payments: list[CardPaymentResponse] = Field(default_factory=list)
    total: Decimal
