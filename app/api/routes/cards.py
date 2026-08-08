"""Credit-card endpoints: register cards, list status, record payments."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.shared.periods import resolve_period
from app.src.auth.dependencies import CurrentUserId
from app.src.cards.dependencies import CreditCardServiceDep
from app.src.cards.dto import (
    CardPaymentRequest,
    CardPaymentResponse,
    CardPaymentsListResponse,
    CreditCardCreateRequest,
    CreditCardResponse,
    CreditCardStatusListResponse,
    CreditCardStatusResponse,
)
from app.src.cards.models import CardPaymentCreate, CreditCardCreate

logger = get_logger(__name__)

router = APIRouter()


@router.post("", response_model=CreditCardResponse)
async def create_card(
    request: CreditCardCreateRequest,
    service: CreditCardServiceDep,
    user_id: CurrentUserId,
) -> CreditCardResponse:
    """Register a credit card (identified by name only, no sensitive data)."""
    card = CreditCardCreate(**request.model_dump())
    created = await service.create_card(card, user_id)
    return CreditCardResponse.from_domain(created)


@router.get("/status", response_model=CreditCardStatusListResponse)
async def get_cards_status(
    service: CreditCardServiceDep,
    user_id: CurrentUserId,
    period: str | None = Query(
        default=None,
        description=(
            "If given ('este_mes', 'mes_pasado', 'todo' or 'YYYY-MM'), every figure "
            "(spent, balance, available, payment date) is reconstructed at that "
            "month-end; otherwise it's the live state today."
        ),
    ),
) -> CreditCardStatusListResponse:
    """Return every card's status (spend, balance, available) for the month or today."""
    period_start, period_end = resolve_period(period) if period else (None, None)
    statuses = await service.get_all_status(
        user_id, period_start=period_start, period_end=period_end
    )
    return CreditCardStatusListResponse(
        cards=[CreditCardStatusResponse.from_domain(s) for s in statuses],
        total_limit=sum((s.card.credit_limit for s in statuses), Decimal("0")),
        total_balance=sum((s.balance for s in statuses), Decimal("0")),
        total_available=sum((s.available for s in statuses), Decimal("0")),
    )


@router.get("/payments", response_model=CardPaymentsListResponse)
async def list_card_payments(
    service: CreditCardServiceDep,
    user_id: CurrentUserId,
    period: str = Query(
        default="este_mes",
        description="Reporting period: 'este_mes', 'mes_pasado', 'todo' or a month 'YYYY-MM'",
    ),
) -> CardPaymentsListResponse:
    """List the card payments made in the period (to show them as events)."""
    start, end = resolve_period(period)
    payments = await service.list_payments(user_id, start, end)
    return CardPaymentsListResponse(
        payments=[CardPaymentResponse.from_domain(p) for p in payments],
        total=sum((p.amount for p in payments), Decimal("0")),
    )


@router.post("/{card_id}/payments", response_model=CreditCardStatusResponse)
async def register_card_payment(
    card_id: str,
    request: CardPaymentRequest,
    service: CreditCardServiceDep,
    user_id: CurrentUserId,
) -> CreditCardStatusResponse:
    """Record a payment toward a card, returning the card's updated status."""
    payment_date = request.payment_date or datetime.now(UTC).date()
    await service.register_payment(
        card_id,
        user_id,
        CardPaymentCreate(amount=request.amount, payment_date=payment_date),
    )
    status = await service.get_status(card_id, user_id)
    return CreditCardStatusResponse.from_domain(status)
