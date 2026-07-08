"""Credit-card use cases: cycle evaluation, balance and payments."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.exceptions import CardNotFoundError
from app.core.logging import get_logger
from app.shared.types import CardId, UserId

from ..cycle import compute_cycle, next_payment_date
from ..interfaces import (
    CardPaymentRepositoryABC,
    CreditCardRepositoryABC,
    CreditCardServiceABC,
    CreditCardSpendingABC,
)
from ..models import (
    CardPayment,
    CardPaymentCreate,
    CardPaymentView,
    CreditCard,
    CreditCardCreate,
    CreditCardStatus,
)

logger = get_logger(__name__)


class CreditCardService(CreditCardServiceABC):
    """Orchestrates card persistence, cycle evaluation, balance and payments."""

    def __init__(
        self,
        repository: CreditCardRepositoryABC,
        payments: CardPaymentRepositoryABC,
        spending: CreditCardSpendingABC,
    ) -> None:
        self._repository = repository
        self._payments = payments
        self._spending = spending

    async def create_card(self, card: CreditCardCreate, user_id: UserId) -> CreditCard:
        return await self._repository.create(card, user_id)

    async def list_cards(self, user_id: UserId) -> list[CreditCard]:
        return await self._repository.list_active(user_id)

    async def get_all_status(
        self, user_id: UserId, as_of: date | None = None
    ) -> list[CreditCardStatus]:
        reference = as_of or _today()
        cards = await self._repository.list_active(user_id)
        return [await self._build_status(card, reference) for card in cards]

    async def get_status(
        self, card_id: CardId, user_id: UserId, as_of: date | None = None
    ) -> CreditCardStatus:
        card = await self._repository.get_by_id(card_id, user_id)
        if card is None:
            raise CardNotFoundError(card_id)
        return await self._build_status(card, as_of or _today())

    async def register_payment(
        self, card_id: CardId, user_id: UserId, payment: CardPaymentCreate
    ) -> CardPayment:
        card = await self._repository.get_by_id(card_id, user_id)
        if card is None:
            raise CardNotFoundError(card_id)
        created = await self._payments.create(payment, card_id, user_id)
        logger.info("Card payment registered", card_id=card_id, user_id=user_id)
        return created

    async def list_payments(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPaymentView]:
        payments = await self._payments.list_in_period(user_id, period_start, period_end)
        cards = await self._repository.list_active(user_id)
        names = {c.id: c.name for c in cards}
        return [
            CardPaymentView(
                card_name=names.get(p.card_id, "Tarjeta"),
                amount=p.amount,
                payment_date=p.payment_date,
            )
            for p in payments
        ]

    async def update_card(
        self,
        card_id: CardId,
        user_id: UserId,
        *,
        name: str | None = None,
        credit_limit: Decimal | None = None,
        cutoff_day: int | None = None,
        payment_day: int | None = None,
    ) -> CreditCard:
        updated = await self._repository.update(
            card_id,
            user_id,
            name=name,
            credit_limit=credit_limit,
            cutoff_day=cutoff_day,
            payment_day=payment_day,
        )
        if updated is None:
            raise CardNotFoundError(card_id)
        return updated

    async def delete_card(self, card_id: CardId, user_id: UserId) -> CreditCard:
        card = await self._repository.deactivate(card_id, user_id)
        if card is None:
            raise CardNotFoundError(card_id)
        logger.info("Card deleted", card_id=card_id, user_id=user_id)
        return card

    async def resolve_by_name(self, name: str, user_id: UserId) -> CreditCard | None:
        target = name.lower().strip()
        if not target:
            return None
        cards = await self._repository.list_active(user_id)
        for card in cards:
            if card.name.lower() == target:
                return card
        for card in cards:
            cname = card.name.lower()
            if target in cname or cname in target:
                return card
        return None

    async def _build_status(
        self, card: CreditCard, reference: date
    ) -> CreditCardStatus:
        cycle_start, cycle_end = compute_cycle(card.cutoff_day, reference)
        charges_total, spent_cycle = await self._spending.charges_summary(
            card.user_id, card.id, cycle_start, reference
        )
        paid_total = await self._payments.total_paid(card.user_id, card.id)

        balance = charges_total - paid_total
        available = card.credit_limit - balance
        utilization = (
            float(balance / card.credit_limit * 100) if card.credit_limit > 0 else 0.0
        )
        return CreditCardStatus(
            card=card,
            cycle_start=cycle_start,
            cycle_end=cycle_end,
            spent_cycle=spent_cycle,
            balance=balance,
            available=available,
            utilization=round(utilization, 2),
            next_payment_date=next_payment_date(card.payment_day, cycle_end),
        )


def _today() -> date:
    return datetime.now(UTC).date()
