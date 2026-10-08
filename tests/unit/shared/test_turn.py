"""Unit tests for the request-scoped chat turn."""

import asyncio

import pytest

from app.shared.turn import TurnContext, bound_turn, current_turn


def test_no_turn_is_bound_by_default() -> None:
    assert current_turn() is None


def test_bound_turn_is_visible_inside_and_restored_after() -> None:
    turn = TurnContext(turn_id="t1", conversation_id="c1")
    with bound_turn(turn):
        assert current_turn() == turn
    assert current_turn() is None


def test_nested_turns_restore_the_outer_one() -> None:
    outer = TurnContext("t1", "c1")
    inner = TurnContext("t2", "c1")
    with bound_turn(outer):
        with bound_turn(inner):
            assert current_turn() == inner
        assert current_turn() == outer


def test_turn_is_restored_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError), bound_turn(TurnContext("t1", "c1")):
        raise RuntimeError("boom")
    assert current_turn() is None


async def test_concurrent_tasks_inherit_the_turn() -> None:
    async def read() -> TurnContext | None:
        return current_turn()

    turn = TurnContext("t1", "c1")
    with bound_turn(turn):
        results = await asyncio.gather(read(), read())
    assert results == [turn, turn]
