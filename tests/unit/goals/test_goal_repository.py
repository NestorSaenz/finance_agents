"""Unit tests for the Supabase goal repository (DB mocked)."""

from datetime import date
from decimal import Decimal

from app.shared.types import CurrencyType, GoalType
from app.src.goals.models import GoalCreate
from app.src.goals.repositories.goal_repository import GoalRepository
from tests.fakes import FakeDatabase, make_goal_row


def _new_goal() -> GoalCreate:
    return GoalCreate(
        name="Viaje a Japón",
        goal_type=GoalType.SAVINGS,
        target_amount=Decimal("100000"),
        currency=CurrencyType.MXN,
        target_date=date(2025, 12, 31),
    )


class TestCreate:
    async def test_persists_and_maps(self) -> None:
        db = FakeDatabase()
        repo = GoalRepository(db)

        result = await repo.create(_new_goal(), "u1")

        inserted = db.inserted[0]
        assert inserted["type"] == "savings"
        assert inserted["target_amount"] == "100000"
        assert inserted["current_amount"] == "0"  # goals are always born at 0
        assert inserted["status"] == "active"
        assert result.target_amount == Decimal("100000.0")
        assert result.goal_type == GoalType.SAVINGS


class TestQueries:
    async def test_get_by_id_returns_none_when_missing(self) -> None:
        repo = GoalRepository(FakeDatabase(rows=[]))
        assert await repo.get_by_id("goal-1", "u1") is None

    async def test_list_orders_by_priority(self) -> None:
        db = FakeDatabase(rows=[make_goal_row()])
        repo = GoalRepository(db)

        await repo.list_page("u1", limit=20, offset=0)

        config = db.select_configs[-1]
        assert config.order_by == "priority"
        assert config.order_ascending is True

    async def test_count(self) -> None:
        rows = [make_goal_row(id=f"goal-{i}") for i in range(3)]
        repo = GoalRepository(FakeDatabase(rows=rows))
        assert await repo.count("u1") == 3


class TestUpdate:
    async def test_update_applies_and_maps(self) -> None:
        db = FakeDatabase(rows=[make_goal_row()])
        repo = GoalRepository(db)

        updated = await repo.update("goal-1", "u1", {"current_amount": 60000.0})

        data, filters = db.updated[-1]
        assert data == {"current_amount": 60000.0}
        assert filters == {"id": "goal-1", "user_id": "u1"}
        assert updated.current_amount == Decimal("60000.0")

    async def test_update_missing_raises(self) -> None:
        from app.core.exceptions import GoalNotFoundError

        class NoRowDB(FakeDatabase):
            async def update(self, table, data, filters):  # type: ignore[no-untyped-def]
                from app.shared.interfaces.database import QueryResult

                return QueryResult(data=[], count=0)

        repo = GoalRepository(NoRowDB())
        import pytest

        with pytest.raises(GoalNotFoundError):
            await repo.update("missing", "u1", {"current_amount": 1.0})
