"""Credit-card use cases: cycle evaluation, balance and payments."""

from datetime import UTC, date, datetime
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Final

from app.core.exceptions import CardNotFoundError
from app.core.logging import get_logger
from app.shared.text_match import normalize
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

# Minimum name similarity (0-1) to resolve a card by a fuzzy/typo'd name. High
# enough that distinct cards don't collide, low enough to catch "rapid"->"rappid".
_FUZZY_MATCH_CUTOFF: Final[float] = 0.8

# All-history window for matching a payment to remove (PostgREST can't range
# filter here, so we fetch and match in Python; personal volumes are small).
_EPOCH: Final[date] = date(1970, 1, 1)
_FAR_FUTURE: Final[date] = date(2999, 12, 31)


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
        self,
        user_id: UserId,
        as_of: date | None = None,
        *,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> list[CreditCardStatus]:
        reference = as_of or _today()
        cards = await self._repository.list_active(user_id)
        return [
            await self._build_status(card, reference, period_start, period_end)
            for card in cards
        ]

    async def get_status(
        self, card_id: CardId, user_id: UserId, as_of: date | None = None
    ) -> CreditCardStatus:
        card = await self._repository.get_by_id(card_id, user_id)
        if card is None:
            raise CardNotFoundError(card_id)
        return await self._build_status(card, as_of or _today())

    async def total_paid_up_to(self, user_id: UserId, as_of: date) -> Decimal:
        return await self._payments.total_paid_up_to(user_id, as_of)

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
                card_id=p.card_id,
                card_name=names.get(p.card_id, "Tarjeta"),
                amount=p.amount,
                payment_date=p.payment_date,
            )
            for p in payments
        ]

    async def remove_payment(
        self,
        user_id: UserId,
        amount: Decimal,
        *,
        payment_date: date | None = None,
        card_id: CardId | None = None,
    ) -> CardPayment | None:
        # One fetch of the user's payments (newest first), matched in Python —
        # mirroring GoalService.remove_contribution. The window spans all history
        # so an older mistaken payment is still found; volumes are small.
        payments = await self._payments.list_in_period(user_id, _EPOCH, _FAR_FUTURE)
        match = next(
            (
                p
                for p in payments
                if p.amount == amount
                and (card_id is None or p.card_id == card_id)
                and (payment_date is None or p.payment_date == payment_date)
            ),
            None,
        )
        if match is None:
            return None
        await self._payments.delete(match.id, user_id)
        logger.info("Card payment removed", card_id=match.card_id, user_id=user_id)
        return match

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
        target = normalize(name)
        if not target:
            return None
        cards = await self._repository.list_active(user_id)
        for card in cards:
            if normalize(card.name) == target:
                return card
        for card in cards:
            cname = normalize(card.name)
            if target in cname or cname in target:
                return card
        # Typo-tolerant fallback: pick the closest name if it's clearly close
        # (e.g. "rapid" -> "rappid"). High cutoff so distinct cards don't collide.
        # Compared on accent-stripped names so "nú"/"nu" don't diverge.
        best, best_ratio = None, 0.0
        for card in cards:
            ratio = SequenceMatcher(None, target, normalize(card.name)).ratio()
            if ratio > best_ratio:
                best, best_ratio = card, ratio
        return best if best_ratio >= _FUZZY_MATCH_CUTOFF else None

    async def _build_status(
        self,
        card: CreditCard,
        reference: date,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> CreditCardStatus:
        # A selected month reconstructs the card "as of" that month-end: cycle,
        # charges and payments are all evaluated at period_end (historical view).
        # With no period we evaluate the live state at `reference` (today).
        historical = period_start is not None and period_end is not None
        # A PAST month is reconstructed at its month-end; the CURRENT month (whose
        # period_end is in the future) must stay live, so cap `as_of` at today —
        # otherwise the cycle/next-payment and balance would jump a cycle ahead.
        as_of: date = min(period_end, reference) if period_end is not None else reference
        period = (
            (period_start, period_end)
            if period_start is not None and period_end is not None
            else None
        )

        cycle_start, cycle_end = compute_cycle(card.cutoff_day, as_of)
        charges_total, cycle_spent, period_spent = await self._spending.charges_summary(
            card.user_id, card.id, cycle_start, as_of, period=period
        )
        paid_total = await self._payments.total_paid(
            card.user_id, card.id, as_of=as_of if historical else None
        )

        # "spent" is the selected month's charges (dashboard) or the current
        # cycle's (chat/card status with no month).
        spent_cycle = period_spent if historical else cycle_spent

        balance = charges_total - paid_total
        # Available never exceeds the limit: overpaying (negative balance) is credit
        # in your favor, not extra spending power. Only a positive balance reduces it.
        positive_balance = max(balance, Decimal("0"))
        available = card.credit_limit - positive_balance
        utilization = (
            float(positive_balance / card.credit_limit * 100)
            if card.credit_limit > 0
            else 0.0
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
