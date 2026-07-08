"""Unit tests for the Supabase budget repository (DB mocked)."""

from datetime import date
from decimal import Decimal

from app.shared.types import BudgetPeriod, CategoryType, CurrencyType
from app.src.budgets.models import BudgetCreate
from app.src.budgets.repositories.budget_repository import BudgetRepository
from tests.fakes import FakeDatabase, make_budget_row


def _new_budget(category: CategoryType | None = CategoryType.RESTAURANTES) -> BudgetCreate:
    return BudgetCreate(
        name="Comida mensual",
        amount=Decimal("300000"),
        category=category,
        currency=CurrencyType.MXN,
        period_type=BudgetPeriod.MONTHLY,
        start_date=date(2024, 12, 1),
        alert_threshold=Decimal("80"),
    )


class TestCreate:
    async def test_persists_and_maps(self) -> None:
        db = FakeDatabase()
        repo = BudgetRepository(db)

        result = await repo.create(_new_budget(), "u1")

        inserted = db.inserted[0]
        assert inserted["amount"] == "300000"
        assert inserted["category"] == "restaurantes"
        assert inserted["period_type"] == "monthly"
        assert inserted["alert_threshold"] == "80"
        assert inserted["is_active"] is True
        assert result.amount == Decimal("300000.0")
        assert result.category == CategoryType.RESTAURANTES

    async def test_overall_budget_persists_null_category(self) -> None:
        db = FakeDatabase()
        repo = BudgetRepository(db)

        await repo.create(_new_budget(category=None), "u1")

        assert db.inserted[0]["category"] is None


class TestQueries:
    async def test_get_by_id_returns_none_when_missing(self) -> None:
        repo = BudgetRepository(FakeDatabase(rows=[]))
        assert await repo.get_by_id("bud-1", "u1") is None

    async def test_get_by_id_maps_null_category_to_none(self) -> None:
        repo = BudgetRepository(FakeDatabase(rows=[make_budget_row(category=None)]))
        budget = await repo.get_by_id("bud-1", "u1")
        assert budget is not None
        assert budget.category is None

    async def test_list_active_filters_active(self) -> None:
        db = FakeDatabase(rows=[make_budget_row()])
        repo = BudgetRepository(db)

        budgets = await repo.list_active("u1")

        assert len(budgets) == 1
        assert db.select_configs[-1].filters == {"user_id": "u1", "is_active": True}

    async def test_count(self) -> None:
        rows = [make_budget_row(id=f"bud-{i}") for i in range(4)]
        repo = BudgetRepository(FakeDatabase(rows=rows))
        assert await repo.count("u1") == 4
