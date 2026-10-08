"""Two-step cutoff/payment-day change: propose in one turn, apply after a later 'sí'."""

from pydantic import ValidationError

from app.core.exceptions import CardNotFoundError, NoActiveTurnError
from app.core.logging import get_logger
from app.shared.turn import current_turn
from app.shared.types import UserId
from app.src.pending.interfaces import PendingActionServiceABC
from app.src.pending.types import PendingActionKind

from ..interfaces import CardScheduleChangeServiceABC, CreditCardServiceABC
from ..models import (
    CardScheduleChange,
    CreditCard,
    ScheduleChangeOutcome,
    ScheduleChangeResult,
    ScheduleProposal,
)

logger = get_logger(__name__)


class CardScheduleChangeService(CardScheduleChangeServiceABC):
    """Enforces, in code, that a schedule change needs the user's later confirmation.

    ``propose`` only stores the intended days (never touches the card). ``confirm``
    consumes the proposal made in an EARLIER turn, re-checks that the card still has
    the days it had when proposed, and only then applies it. Everything is scoped by
    ``user_id``; the model never sees ids.
    """

    def __init__(self, cards: CreditCardServiceABC, pending: PendingActionServiceABC) -> None:
        self._cards = cards
        self._pending = pending

    async def propose(
        self,
        card: CreditCard,
        user_id: UserId,
        cutoff_day: int | None,
        payment_day: int | None,
    ) -> ScheduleProposal | None:
        turn = current_turn()
        if turn is None:
            raise NoActiveTurnError()

        change = CardScheduleChange(
            card_id=card.id,
            cutoff_day=cutoff_day if cutoff_day != card.cutoff_day else None,
            payment_day=payment_day if payment_day != card.payment_day else None,
            prev_cutoff_day=card.cutoff_day,
            prev_payment_day=card.payment_day,
        )
        if change.cutoff_day is None and change.payment_day is None:
            return None

        stored = await self._pending.propose(
            user_id, turn, PendingActionKind.CARD_SCHEDULE, change.model_dump(mode="json")
        )
        return ScheduleProposal(change, already_pending=not stored)

    async def confirm(self, user_id: UserId) -> ScheduleChangeResult:
        turn = current_turn()
        if turn is None:
            raise NoActiveTurnError()

        payload = await self._pending.consume(user_id, turn, PendingActionKind.CARD_SCHEDULE)
        if payload is None:
            return ScheduleChangeResult(ScheduleChangeOutcome.NONE_PENDING)
        try:
            change = CardScheduleChange.model_validate(payload)
        except ValidationError as e:
            logger.warning("Discarding malformed pending card schedule", error=str(e))
            return ScheduleChangeResult(ScheduleChangeOutcome.NONE_PENDING)

        cards = await self._cards.list_cards(user_id)
        card = next((c for c in cards if c.id == change.card_id), None)
        if card is None:
            return ScheduleChangeResult(ScheduleChangeOutcome.NOT_FOUND)
        if (card.cutoff_day, card.payment_day) != (
            change.prev_cutoff_day,
            change.prev_payment_day,
        ):
            return ScheduleChangeResult(ScheduleChangeOutcome.STALE)

        try:
            updated = await self._cards.update_card(
                card.id,
                user_id,
                cutoff_day=change.cutoff_day,
                payment_day=change.payment_day,
            )
        except CardNotFoundError:
            return ScheduleChangeResult(ScheduleChangeOutcome.NOT_FOUND)
        return ScheduleChangeResult(ScheduleChangeOutcome.APPLIED, card, updated)
