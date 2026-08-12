"""Unit tests for the goal-contribution repository (Supabase mocked)."""

from datetime import date

import pytest

from app.src.goals.repositories.goal_contribution_repository import (
    GoalContributionRepository,
)
from tests.fakes import FakeDatabase

pytestmark = pytest.mark.asyncio


def _row(
    contribution_date: str, amount: float, goal_id: str = "goal-1"
) -> dict[str, object]:
    return {
        "id": f"c-{contribution_date}",
        "user_id": "u1",
        "goal_id": goal_id,
        "amount": amount,
        "contribution_date": contribution_date,
        "created_at": "2026-07-01T10:00:00+00:00",
    }


async def test_list_in_period_keeps_only_the_date_window() -> None:
    # May (before) and August (after) fall outside a June window; two June ones stay.
    db = FakeDatabase(
        rows=[
            _row("2026-05-31", 200.0),
            _row("2026-06-10", 300.0),
            _row("2026-06-20", 400.0, goal_id="goal-2"),
            _row("2026-08-01", 500.0),
        ]
    )
    repo = GoalContributionRepository(db)  # type: ignore[arg-type]

    result = await repo.list_in_period("u1", date(2026, 6, 1), date(2026, 6, 30))

    dates = {c.contribution_date for c in result}
    assert dates == {date(2026, 6, 10), date(2026, 6, 20)}
    assert {c.goal_id for c in result} == {"goal-1", "goal-2"}


async def test_list_in_period_is_inclusive_at_both_bounds() -> None:
    db = FakeDatabase(
        rows=[
            _row("2026-06-01", 100.0),
            _row("2026-06-30", 200.0),
        ]
    )
    repo = GoalContributionRepository(db)  # type: ignore[arg-type]

    result = await repo.list_in_period("u1", date(2026, 6, 1), date(2026, 6, 30))

    assert len(result) == 2  # both endpoints included


async def test_list_in_period_empty_without_contributions() -> None:
    repo = GoalContributionRepository(FakeDatabase(rows=[]))  # type: ignore[arg-type]

    assert await repo.list_in_period("u1", date(2026, 6, 1), date(2026, 6, 30)) == []
