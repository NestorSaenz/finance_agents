"""Domain models for the credit-cards module."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import NamedTuple

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
    """A card payment enriched with the card's id and name (for display).

    ``card_id`` lets a consumer associate the payment with a specific card even
    when two cards share a name (names are not unique).
    """

    card_id: str
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
    # TOTAL debt = every charge - every payment (up to the eval date). It includes
    # the open cycle's charges, so it is NOT the amount due on next_payment_date.
    balance: Decimal
    available: Decimal  # credit_limit - max(balance, 0)
    utilization: float  # percentage of the limit used by the balance (0-100)
    # Next payment due on/after the eval date. It may settle an already-CLOSED
    # statement (e.g. cutoff 19, pay 2, today Oct 1 -> Oct 2), not the open cycle.
    next_payment_date: date
    # Due date of the OPEN cycle's statement (cycle_start..cycle_end); equals
    # next_payment_date when no closed statement is still pending.
    cycle_payment_date: date
    # Statement period settled on next_payment_date. Live view only: None in a
    # historical (selected-month) view, where a month spans two statements.
    statement_start: date | None = None
    statement_end: date | None = None
    # Amount to pay on next_payment_date = unpaid charges up to the last cutoff
    # (includes any older unpaid statement). None when that statement hasn't
    # closed yet (its amount isn't final) or in a historical view.
    statement_amount: Decimal | None = None
    # Unpaid charges from statements whose due date already PASSED. Only set when
    # next_payment_date belongs to the open cycle (otherwise it's part of
    # statement_amount); None in a historical view.
    overdue_amount: Decimal | None = None


class CardScheduleChange(BaseModel):
    """A proposed change to a card's cutoff and/or payment day, awaiting confirmation.

    ``None`` leaves that day unchanged. ``prev_*`` snapshot the card's days when the
    change was proposed, so confirming can detect that they changed in the meantime.
    """

    card_id: str
    cutoff_day: int | None = Field(default=None, ge=1, le=31)
    payment_day: int | None = Field(default=None, ge=1, le=31)
    prev_cutoff_day: int = Field(..., ge=1, le=31)
    prev_payment_day: int = Field(..., ge=1, le=31)


class ScheduleProposal(NamedTuple):
    """A stored proposal; ``already_pending`` when an identical earlier one was kept."""

    change: CardScheduleChange
    already_pending: bool


class ScheduleChangeOutcome(StrEnum):
    """Result of confirming a proposed schedule change."""

    APPLIED = "applied"
    NONE_PENDING = "none_pending"
    STALE = "stale"
    NOT_FOUND = "not_found"


class ScheduleChangeResult(NamedTuple):
    """Outcome of a confirmation plus the card before/after (only when applied)."""

    outcome: ScheduleChangeOutcome
    before: CreditCard | None = None
    after: CreditCard | None = None
