"""Unit tests for the goal-plan repository (database mocked)."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import InfrastructureError
from app.shared.interfaces.database import QueryResult
from app.shared.types import GoalPlanKind
from app.src.goals.constants import GOAL_PLANS_CONFLICT, GOAL_PLANS_TABLE
from app.src.goals.repositories.goal_plan_repository import GoalPlanRepository
from tests.fakes import FakeDatabase

pytestmark = pytest.mark.asyncio


def _row(kind: str = "recurring", month: str = "2026-06-01", amount: str = "500.50") -> dict[str, object]:
    return {
        "id": "plan-1",
        "goal_id": "goal-1",
        "user_id": "u1",
        "month": month,
        "planned_amount": amount,
        "kind": kind,
        "created_at": "2026-06-01T10:00:00+00:00",
        "updated_at": "2026-06-01T10:00:00+00:00",
    }


async def test_list_for_user_maps_rows_to_domain_plans() -> None:
    db = FakeDatabase(rows=[_row(), _row(kind="override", month="2026-07-01", amount="0")])
    repo = GoalPlanRepository(db)  # type: ignore[arg-type]

    plans = await repo.list_for_user("u1")

    assert [(p.kind, p.month, p.planned_amount) for p in plans] == [
        (GoalPlanKind.RECURRING, date(2026, 6, 1), Decimal("500.50")),
        (GoalPlanKind.OVERRIDE, date(2026, 7, 1), Decimal("0")),
    ]
    config = db.select_configs[0]
    assert config is not None
    assert config.filters == {"user_id": "u1"}
    assert config.order_by == "month"


async def test_list_for_goal_filters_by_user_and_goal() -> None:
    db = FakeDatabase(rows=[_row()])
    repo = GoalPlanRepository(db)  # type: ignore[arg-type]

    await repo.list_for_goal("u1", "goal-1")

    config = db.select_configs[0]
    assert config is not None
    assert config.filters == {"user_id": "u1", "goal_id": "goal-1"}


class _IdAssigningDatabase(FakeDatabase):
    """Upsert echoes the row back with the id Postgres would generate."""

    async def upsert(self, table: str, data: object, on_conflict: str) -> QueryResult:
        await super().upsert(table, data, on_conflict)
        assert isinstance(data, dict)
        return QueryResult(data=[{**data, "id": "plan-1"}], count=1)


async def test_upsert_uses_the_unique_key_and_sends_the_amount_as_exact_string() -> None:
    db = _IdAssigningDatabase()
    repo = GoalPlanRepository(db)  # type: ignore[arg-type]

    plan = await repo.upsert("u1", "goal-1", date(2026, 6, 1), GoalPlanKind.OVERRIDE, Decimal("500.50"))

    assert db.upsert_calls == [(GOAL_PLANS_TABLE, GOAL_PLANS_CONFLICT)]
    sent = db.upserted[0]
    assert sent["goal_id"] == "goal-1"
    assert sent["user_id"] == "u1"
    assert sent["month"] == "2026-06-01"
    assert sent["kind"] == "override"
    assert sent["planned_amount"] == "500.50"  # never a float
    assert "updated_at" in sent
    assert plan.kind == GoalPlanKind.OVERRIDE
    assert plan.goal_id == "goal-1"


async def test_upsert_without_rows_back_raises() -> None:
    class EmptyUpsertDatabase(FakeDatabase):
        async def upsert(self, table: str, data: object, on_conflict: str) -> QueryResult:
            return QueryResult(data=[], count=0)

    repo = GoalPlanRepository(EmptyUpsertDatabase())  # type: ignore[arg-type]

    with pytest.raises(InfrastructureError):
        await repo.upsert("u1", "goal-1", date(2026, 6, 1), GoalPlanKind.RECURRING, Decimal("1"))


async def test_unknown_kind_is_an_error_not_a_silent_override() -> None:
    db = FakeDatabase(rows=[_row(kind="mensual")])
    repo = GoalPlanRepository(db)  # type: ignore[arg-type]

    with pytest.raises(InfrastructureError):
        await repo.list_for_user("u1")


async def test_delete_targets_exactly_one_row_scoped_to_the_user() -> None:
    db = FakeDatabase()
    repo = GoalPlanRepository(db)  # type: ignore[arg-type]

    await repo.delete("u1", "goal-1", date(2026, 6, 1), GoalPlanKind.OVERRIDE)

    assert db.deleted == [
        {"user_id": "u1", "goal_id": "goal-1", "month": "2026-06-01", "kind": "override"}
    ]
