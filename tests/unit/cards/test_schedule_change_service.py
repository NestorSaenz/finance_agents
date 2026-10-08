"""Unit tests for the two-step (propose, then confirm) card schedule change."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.exceptions import NoActiveTurnError
from app.shared.turn import TurnContext, bound_turn
from app.src.cards.models import CardScheduleChange, CreditCard, ScheduleChangeOutcome
from app.src.cards.services.schedule_change_service import CardScheduleChangeService
from app.src.pending.constants import PENDING_ACTION_TTL
from app.src.pending.services.pending_action_service import PendingActionService
from app.src.pending.types import PendingActionKind
from tests.fakes import FakePendingActionRepository, InMemoryCardService


def _card(user_id: str = "u1", card_id: str = "card-1") -> CreditCard:
    return CreditCard(
        id=card_id,
        user_id=user_id,
        name="Rappi",
        credit_limit=Decimal("5000000"),
        cutoff_day=19,
        payment_day=2,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _turn(turn_id: str, conversation_id: str = "conv-1") -> TurnContext:
    return TurnContext(turn_id=turn_id, conversation_id=conversation_id)


@pytest.fixture
def cards() -> InMemoryCardService:
    return InMemoryCardService([_card()])


@pytest.fixture
def repo() -> FakePendingActionRepository:
    return FakePendingActionRepository()


@pytest.fixture
def service(
    cards: InMemoryCardService, repo: FakePendingActionRepository
) -> CardScheduleChangeService:
    return CardScheduleChangeService(cards, PendingActionService(repo))


class TestCardScheduleChangeModel:
    @pytest.mark.parametrize("day", [0, 32, -1])
    def test_rejects_out_of_range_days(self, day: int) -> None:
        with pytest.raises(ValidationError):
            CardScheduleChange(card_id="c", cutoff_day=day, prev_cutoff_day=19, prev_payment_day=2)
        with pytest.raises(ValidationError):
            CardScheduleChange(card_id="c", payment_day=day, prev_cutoff_day=19, prev_payment_day=2)

    def test_accepts_the_bounds(self) -> None:
        change = CardScheduleChange(
            card_id="c", cutoff_day=1, payment_day=31, prev_cutoff_day=19, prev_payment_day=2
        )
        assert (change.cutoff_day, change.payment_day) == (1, 31)


class TestPropose:
    async def test_stores_the_proposal_and_does_not_touch_the_card(
        self,
        service: CardScheduleChangeService,
        cards: InMemoryCardService,
        repo: FakePendingActionRepository,
    ) -> None:
        with bound_turn(_turn("t1")):
            proposal = await service.propose(_card(), "u1", 20, None)

        assert proposal is not None
        assert not proposal.already_pending
        change = proposal.change
        assert (change.cutoff_day, change.payment_day) == (20, None)
        assert (change.prev_cutoff_day, change.prev_payment_day) == (19, 2)
        assert cards.update_calls == 0
        assert cards.cards[0].cutoff_day == 19
        assert repo.rows[("u1", "conv-1")].payload["card_id"] == "card-1"

    async def test_same_values_propose_nothing(
        self, service: CardScheduleChangeService, repo: FakePendingActionRepository
    ) -> None:
        with bound_turn(_turn("t1")):
            change = await service.propose(_card(), "u1", 19, 2)

        assert change is None
        assert repo.rows == {}

    async def test_only_the_differing_day_is_proposed(
        self, service: CardScheduleChangeService
    ) -> None:
        with bound_turn(_turn("t1")):
            proposal = await service.propose(_card(), "u1", 19, 5)

        assert proposal is not None
        assert (proposal.change.cutoff_day, proposal.change.payment_day) == (None, 5)

    async def test_fails_closed_without_a_bound_turn(
        self, service: CardScheduleChangeService, repo: FakePendingActionRepository
    ) -> None:
        with pytest.raises(NoActiveTurnError):
            await service.propose(_card(), "u1", 20, None)
        assert repo.rows == {}


class TestRepropose:
    async def test_identical_repropose_in_the_confirming_turn_keeps_the_proposal(
        self, service: CardScheduleChangeService, cards: InMemoryCardService
    ) -> None:
        with bound_turn(_turn("t1")):
            await service.propose(_card(), "u1", 20, None)
        with bound_turn(_turn("t2")):
            again = await service.propose(_card(), "u1", 20, None)
            result = await service.confirm("u1")

        assert again is not None
        assert again.already_pending
        assert result.outcome is ScheduleChangeOutcome.APPLIED
        assert cards.cards[0].cutoff_day == 20

    async def test_different_repropose_overwrites_and_needs_a_later_turn(
        self, service: CardScheduleChangeService, cards: InMemoryCardService
    ) -> None:
        with bound_turn(_turn("t1")):
            await service.propose(_card(), "u1", 20, None)
        with bound_turn(_turn("t2")):
            other = await service.propose(_card(), "u1", 25, None)
            same_turn = await service.confirm("u1")
        with bound_turn(_turn("t3")):
            later = await service.confirm("u1")

        assert other is not None
        assert not other.already_pending
        assert same_turn.outcome is ScheduleChangeOutcome.NONE_PENDING
        assert later.outcome is ScheduleChangeOutcome.APPLIED
        assert cards.cards[0].cutoff_day == 25

    async def test_identical_repropose_in_the_same_turn_is_a_plain_overwrite(
        self, service: CardScheduleChangeService
    ) -> None:
        with bound_turn(_turn("t1")):
            await service.propose(_card(), "u1", 20, None)
            again = await service.propose(_card(), "u1", 20, None)

        assert again is not None
        assert not again.already_pending


class TestConfirm:
    async def test_same_turn_confirm_is_none_pending_and_card_unchanged(
        self, service: CardScheduleChangeService, cards: InMemoryCardService
    ) -> None:
        with bound_turn(_turn("t1")):
            await service.propose(_card(), "u1", 20, None)
            result = await service.confirm("u1")

        assert result.outcome is ScheduleChangeOutcome.NONE_PENDING
        assert cards.cards[0].cutoff_day == 19

    async def test_next_turn_applies_once_then_nothing_is_pending(
        self,
        service: CardScheduleChangeService,
        cards: InMemoryCardService,
        repo: FakePendingActionRepository,
    ) -> None:
        with bound_turn(_turn("t1")):
            await service.propose(_card(), "u1", 20, 5)
        with bound_turn(_turn("t2")):
            result = await service.confirm("u1")
            again = await service.confirm("u1")

        assert result.outcome is ScheduleChangeOutcome.APPLIED
        assert result.before is not None
        assert result.after is not None
        assert (result.before.cutoff_day, result.after.cutoff_day) == (19, 20)
        assert (result.before.payment_day, result.after.payment_day) == (2, 5)
        assert (cards.cards[0].cutoff_day, cards.cards[0].payment_day) == (20, 5)
        assert repo.rows == {}
        assert again.outcome is ScheduleChangeOutcome.NONE_PENDING
        assert cards.update_calls == 1

    async def test_expired_proposal_is_none_pending(
        self,
        service: CardScheduleChangeService,
        cards: InMemoryCardService,
        repo: FakePendingActionRepository,
    ) -> None:
        with bound_turn(_turn("t1")):
            await service.propose(_card(), "u1", 20, None)
        repo.now += PENDING_ACTION_TTL + timedelta(seconds=1)
        with bound_turn(_turn("t2")):
            result = await service.confirm("u1")

        assert result.outcome is ScheduleChangeOutcome.NONE_PENDING
        assert cards.cards[0].cutoff_day == 19

    async def test_other_conversation_cannot_confirm(
        self, service: CardScheduleChangeService, cards: InMemoryCardService
    ) -> None:
        with bound_turn(_turn("t1", "conv-1")):
            await service.propose(_card(), "u1", 20, None)
        with bound_turn(_turn("t2", "conv-2")):
            result = await service.confirm("u1")

        assert result.outcome is ScheduleChangeOutcome.NONE_PENDING
        assert cards.cards[0].cutoff_day == 19

    async def test_other_user_cannot_confirm(
        self, service: CardScheduleChangeService, cards: InMemoryCardService
    ) -> None:
        with bound_turn(_turn("t1")):
            await service.propose(_card(), "u1", 20, None)
        with bound_turn(_turn("t2")):
            result = await service.confirm("u2")

        assert result.outcome is ScheduleChangeOutcome.NONE_PENDING
        assert cards.cards[0].cutoff_day == 19

    async def test_snapshot_mismatch_is_stale_and_changes_nothing(
        self, service: CardScheduleChangeService, cards: InMemoryCardService
    ) -> None:
        with bound_turn(_turn("t1")):
            await service.propose(_card(), "u1", 20, None)
        cards.cards[0] = cards.cards[0].model_copy(update={"cutoff_day": 7})
        with bound_turn(_turn("t2")):
            result = await service.confirm("u1")

        assert result.outcome is ScheduleChangeOutcome.STALE
        assert cards.cards[0].cutoff_day == 7
        assert cards.update_calls == 0

    async def test_deleted_card_is_not_found(
        self, service: CardScheduleChangeService, cards: InMemoryCardService
    ) -> None:
        with bound_turn(_turn("t1")):
            await service.propose(_card(), "u1", 20, None)
        cards.cards[0] = cards.cards[0].model_copy(update={"is_active": False})
        with bound_turn(_turn("t2")):
            result = await service.confirm("u1")

        assert result.outcome is ScheduleChangeOutcome.NOT_FOUND

    async def test_malformed_payload_is_discarded_as_none_pending(
        self,
        service: CardScheduleChangeService,
        cards: InMemoryCardService,
        repo: FakePendingActionRepository,
    ) -> None:
        await PendingActionService(repo).propose(
            "u1", _turn("t1"), PendingActionKind.CARD_SCHEDULE, {"card_id": "card-1"}
        )
        with bound_turn(_turn("t2")):
            result = await service.confirm("u1")

        assert result.outcome is ScheduleChangeOutcome.NONE_PENDING
        assert cards.update_calls == 0

    async def test_fails_closed_without_a_bound_turn(
        self, service: CardScheduleChangeService
    ) -> None:
        with pytest.raises(NoActiveTurnError):
            await service.confirm("u1")
