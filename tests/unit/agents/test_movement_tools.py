"""Unit tests for the movement-search toolkit (finder stubbed)."""

from datetime import date
from decimal import Decimal
from typing import cast

import pytest

from app.agents.tools.movement_tools import MovementToolkit
from app.shared.types import MovementKind, UserId
from app.src.analysis.interfaces import MovementFinderServiceABC
from app.src.analysis.models import MovementCandidate

pytestmark = pytest.mark.asyncio


class _StubFinder:
    def __init__(self, candidates: list[MovementCandidate]) -> None:
        self._candidates = candidates
        self.received: dict[str, object] = {}

    async def find_movements(
        self,
        user_id: str,
        *,
        amount: Decimal | None = None,
        on_date: date | None = None,
        text: str | None = None,
        today: date | None = None,
    ) -> list[MovementCandidate]:
        self.received = {"amount": amount, "on_date": on_date, "text": text}
        return self._candidates


def _toolkit(candidates: list[MovementCandidate]) -> tuple[MovementToolkit, _StubFinder]:
    stub = _StubFinder(candidates)
    return MovementToolkit(cast(MovementFinderServiceABC, stub)), stub


async def test_find_lists_candidate_with_kind() -> None:
    toolkit, _ = _toolkit(
        [
            MovementCandidate(
                kind=MovementKind.GOAL_CONTRIBUTION,
                label="Fondo de Emergencias",
                amount=Decimal("8915400"),
                date=date(2026, 8, 12),
            )
        ]
    )
    result = await toolkit.dispatch("find_movements", {"amount": 8915400}, "u1")
    assert "aporte a meta" in result.lower()
    assert "Fondo de Emergencias" in result
    assert "remove_goal_contribution" in result  # routing hint


async def test_find_requires_a_filter() -> None:
    toolkit, stub = _toolkit([])
    result = await toolkit.dispatch("find_movements", {}, "u1")
    assert "¿qué movimiento" in result.lower()
    assert stub.received == {}  # finder never called


async def test_find_empty_result_message() -> None:
    toolkit, _ = _toolkit([])
    result = await toolkit.dispatch("find_movements", {"amount": 999}, "u1")
    assert "no encontré" in result.lower()


async def test_find_passes_parsed_args() -> None:
    toolkit, stub = _toolkit([])
    await toolkit.dispatch(
        "find_movements",
        {"amount": 1000, "date": "2026-08-12", "text": "emergencia"},
        "u1",
    )
    assert stub.received["amount"] == Decimal("1000")
    assert stub.received["on_date"] == date(2026, 8, 12)
    assert stub.received["text"] == "emergencia"


async def test_zero_amount_treated_as_absent() -> None:
    # A 0/negative amount is not a valid filter; with no other filter → ask.
    toolkit, stub = _toolkit([])
    result = await toolkit.dispatch("find_movements", {"amount": 0}, "u1")
    assert "¿qué movimiento" in result.lower()
    assert stub.received == {}


async def test_unknown_tool_raises() -> None:
    toolkit, _ = _toolkit([])
    with pytest.raises(ValueError, match="Unknown movement tool"):
        await toolkit.dispatch("nope", {}, cast(UserId, "u1"))
