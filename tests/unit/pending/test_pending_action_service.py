"""Unit tests for the pending-action service over the RPC-faithful in-memory store."""

from datetime import timedelta

import pytest

from app.shared.turn import TurnContext
from app.src.pending.constants import PENDING_ACTION_TTL
from app.src.pending.services.pending_action_service import PendingActionService
from app.src.pending.types import PendingActionKind
from tests.fakes import FakePendingActionRepository

KIND = PendingActionKind.CARD_SCHEDULE
PAYLOAD: dict[str, object] = {"card_id": "c-1", "cutoff_day": 20}


def _turn(turn_id: str, conversation_id: str = "conv-1") -> TurnContext:
    return TurnContext(turn_id=turn_id, conversation_id=conversation_id)


@pytest.fixture
def repo() -> FakePendingActionRepository:
    return FakePendingActionRepository()


@pytest.fixture
def service(repo: FakePendingActionRepository) -> PendingActionService:
    return PendingActionService(repo)


async def test_propose_stores_a_row_with_the_ttl(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    await service.propose("u1", _turn("t1"), KIND, PAYLOAD)

    row = repo.rows[("u1", "conv-1")]
    assert row.turn_id == "t1"
    assert row.payload == PAYLOAD
    assert row.expires_at - row.created_at == PENDING_ACTION_TTL


async def test_same_turn_cannot_consume_its_own_proposal(service: PendingActionService) -> None:
    await service.propose("u1", _turn("t1"), KIND, PAYLOAD)

    assert await service.consume("u1", _turn("t1"), KIND) is None


async def test_next_turn_consumes_once(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    await service.propose("u1", _turn("t1"), KIND, PAYLOAD)

    assert await service.consume("u1", _turn("t2"), KIND) == PAYLOAD
    assert repo.rows == {}
    assert await service.consume("u1", _turn("t2"), KIND) is None  # replay-safe


async def test_expired_proposal_is_not_consumable(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    await service.propose("u1", _turn("t1"), KIND, PAYLOAD)
    repo.now += PENDING_ACTION_TTL + timedelta(seconds=1)

    assert await service.consume("u1", _turn("t2"), KIND) is None
    assert repo.rows == {}  # expired rows are cleaned up too


async def test_other_conversation_cannot_consume(service: PendingActionService) -> None:
    await service.propose("u1", _turn("t1", "conv-1"), KIND, PAYLOAD)

    assert await service.consume("u1", _turn("t2", "conv-2"), KIND) is None


async def test_other_user_cannot_consume(service: PendingActionService) -> None:
    await service.propose("u1", _turn("t1"), KIND, PAYLOAD)

    assert await service.consume("u2", _turn("t2"), KIND) is None
    assert await service.consume("u1", _turn("t2"), KIND) == PAYLOAD


async def test_a_new_proposal_replaces_the_previous_one(service: PendingActionService) -> None:
    await service.propose("u1", _turn("t1"), KIND, {"cutoff_day": 20})
    await service.propose("u1", _turn("t2"), KIND, {"cutoff_day": 25})

    assert await service.consume("u1", _turn("t3"), KIND) == {"cutoff_day": 25}


async def test_discard_stale_keeps_the_current_turns_row(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    await service.propose("u1", _turn("t1"), KIND, PAYLOAD)

    await service.discard_stale("u1", _turn("t1"))

    assert ("u1", "conv-1") in repo.rows


async def test_discard_stale_removes_older_turns(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    await service.propose("u1", _turn("t1"), KIND, PAYLOAD)

    await service.discard_stale("u1", _turn("t2"))

    assert repo.rows == {}
    assert await service.consume("u1", _turn("t3"), KIND) is None


async def test_discard_stale_leaves_other_conversations_alone(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    await service.propose("u1", _turn("t1", "conv-1"), KIND, PAYLOAD)

    await service.discard_stale("u1", _turn("t2", "conv-2"))

    assert ("u1", "conv-1") in repo.rows


async def test_discard_stale_drops_the_users_expired_rows_in_any_conversation(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    await service.propose("u1", _turn("t1", "conv-1"), KIND, PAYLOAD)
    repo.now += PENDING_ACTION_TTL + timedelta(minutes=1)

    await service.discard_stale("u1", _turn("t2", "conv-2"))

    assert repo.rows == {}


async def test_identical_proposal_from_an_earlier_turn_is_left_untouched(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    assert await service.propose("u1", _turn("t1"), KIND, PAYLOAD) is True
    assert await service.propose("u1", _turn("t2"), KIND, PAYLOAD) is False

    assert repo.rows[("u1", "conv-1")].turn_id == "t1"
    assert await service.consume("u1", _turn("t2"), KIND) == PAYLOAD


async def test_expired_identical_proposal_is_replaced(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    await service.propose("u1", _turn("t1"), KIND, PAYLOAD)
    # The service compares against the real clock, so age the stored row itself.
    row = repo.rows[("u1", "conv-1")]
    repo.rows[("u1", "conv-1")] = row.model_copy(
        update={"expires_at": row.created_at - timedelta(seconds=1)}
    )

    assert await service.propose("u1", _turn("t2"), KIND, PAYLOAD) is True
    assert repo.rows[("u1", "conv-1")].turn_id == "t2"


async def test_discard_stale_without_keep_current_drops_this_turns_row_too(
    service: PendingActionService, repo: FakePendingActionRepository
) -> None:
    await service.propose("u1", _turn("t1"), KIND, PAYLOAD)

    await service.discard_stale("u1", _turn("t1"), keep_current=False)

    assert repo.rows == {}
    assert await service.consume("u1", _turn("t2"), KIND) is None
