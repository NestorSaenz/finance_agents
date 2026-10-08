"""Unit tests for the Supabase-backed pending-action repository (RPC contract)."""

from datetime import UTC, datetime
from typing import Any

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import DatabaseQueryError
from app.shared.interfaces.database import QueryResult
from app.src.pending.constants import (
    CONSUME_PENDING_ACTION_RPC,
    DISCARD_STALE_PENDING_ACTIONS_RPC,
    PENDING_ACTIONS_TABLE,
)
from app.src.pending.models import PendingAction
from app.src.pending.repositories.pending_action_repository import PendingActionRepository
from app.src.pending.types import PendingActionKind
from tests.fakes import FakeDatabase

KIND = PendingActionKind.CARD_SCHEDULE
NOW = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)


class FailingDatabase(FakeDatabase):
    async def execute_rpc(
        self, function_name: str, params: dict[str, Any] | None = None
    ) -> QueryResult:
        raise APIError({"message": "boom"})

    async def upsert(self, table: str, data: Any, on_conflict: str) -> QueryResult:
        raise APIError({"message": "boom"})


def _action(payload: dict[str, object] | None = None) -> PendingAction:
    return PendingAction(
        user_id="u1",
        conversation_id="c1",
        kind=KIND,
        payload=payload or {},
        turn_id="t1",
        created_at=NOW,
        expires_at=NOW,
    )


async def test_upsert_writes_one_row_per_user_and_conversation() -> None:
    db = FakeDatabase()

    await PendingActionRepository(db).upsert(_action({"cutoff_day": 20}))

    assert db.upsert_calls == [(PENDING_ACTIONS_TABLE, "user_id,conversation_id")]
    row = db.upserted[0]
    assert row["kind"] == "card_schedule"
    assert row["payload"] == {"cutoff_day": 20}
    assert row["turn_id"] == "t1"


async def test_consume_calls_the_rpc_and_returns_the_payload() -> None:
    db = FakeDatabase()
    db.rpc_result = [{"cutoff_day": 20}]

    payload = await PendingActionRepository(db).consume("u1", "c1", KIND, "t2")

    assert payload == {"cutoff_day": 20}
    assert db.rpc_calls[-1] == (
        CONSUME_PENDING_ACTION_RPC,
        {
            "p_user_id": "u1",
            "p_conversation_id": "c1",
            "p_kind": "card_schedule",
            "p_turn_id": "t2",
        },
    )


@pytest.mark.parametrize("rows", [[], [None]])
async def test_consume_returns_none_when_nothing_matches(rows: list[Any]) -> None:
    db = FakeDatabase()
    db.rpc_result = rows

    assert await PendingActionRepository(db).consume("u1", "c1", KIND, "t2") is None


async def test_discard_stale_calls_the_rpc() -> None:
    db = FakeDatabase()

    await PendingActionRepository(db).discard_stale("u1", "c1", "t2")

    assert db.rpc_calls[-1] == (
        DISCARD_STALE_PENDING_ACTIONS_RPC,
        {"p_user_id": "u1", "p_conversation_id": "c1", "p_keep_turn_id": "t2"},
    )


async def test_raw_client_failures_surface_as_database_errors() -> None:
    repo = PendingActionRepository(FailingDatabase())

    with pytest.raises(DatabaseQueryError):
        await repo.upsert(_action())
    with pytest.raises(DatabaseQueryError):
        await repo.consume("u1", "c1", KIND, "t2")
    with pytest.raises(DatabaseQueryError):
        await repo.discard_stale("u1", "c1", "t2")


@pytest.mark.parametrize("rows", [[["not", "a", "dict"]], ["scalar"]])
async def test_consume_ignores_non_dict_results(rows: list[Any]) -> None:
    db = FakeDatabase()
    db.rpc_result = rows

    assert await PendingActionRepository(db).consume("u1", "c1", KIND, "t2") is None


async def test_get_returns_the_stored_row_or_none() -> None:
    db = FakeDatabase()
    assert await PendingActionRepository(db).get("u1", "c1") is None

    db.rows = [
        {
            "user_id": "u1",
            "conversation_id": "c1",
            "kind": "card_schedule",
            "payload": {"cutoff_day": 20},
            "turn_id": "t1",
            "created_at": NOW.isoformat(),
            "expires_at": NOW.isoformat(),
        }
    ]
    action = await PendingActionRepository(db).get("u1", "c1")

    assert action is not None
    assert action.turn_id == "t1"
    assert action.payload == {"cutoff_day": 20}
