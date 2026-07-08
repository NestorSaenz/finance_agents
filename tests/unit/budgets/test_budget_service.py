"""Unit tests for the budget service (repository + spending mocked)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.exceptions import BudgetNotFoundError
from app.shared.types import BudgetId, BudgetPeriod, CategoryType, CurrencyType, UserId
from app.src.budgets.interfaces import BudgetRepositoryABC, BudgetSpendingABC
from app.src.budgets.models import Budget, BudgetCreate
from app.src.budgets.services.budget_service import BudgetService


def _budget(
    amount: Decimal = Decimal("1000"),
    alert_threshold: Decimal = Decimal("80"),
    alert_enabled: bool = True,
) -> Budget:
    return Budget(
        id="bud-1",
        user_id="u1",
        name="Comida",
        amount=amount,
        category=CategoryType.RESTAURANTES,
        currency=CurrencyType.MXN,
        period_type=BudgetPeriod.MONTHLY,
        start_date=date(2024, 12, 1),
        end_date=None,
        alert_threshold=alert_threshold,
        alert_enabled=alert_enabled,
        is_active=True,
        created_at=datetime.now(UTC),
    )


class FakeSpending(BudgetSpendingABC):
    def __init__(self, spent: Decimal) -> None:
        self.spent = spent

    async def get_spent(self, user_id, category, period_start, period_end) -> Decimal:  # type: ignore[no-untyped-def]
        return self.spent


class FakeBudgetRepository(BudgetRepositoryABC):
    def __init__(self, budget: Budget | None = None, active: list[Budget] | None = None) -> None:
        self.budget = budget
        self.active = active or []
        self.created: list[BudgetCreate] = []

    async def create(self, budget: BudgetCreate, user_id: UserId) -> Budget:
        self.created.append(budget)
        return _budget(amount=budget.amount)

    async def get_by_id(self, budget_id: BudgetId, user_id: UserId) -> Budget | None:
        return self.budget

    async def list_page(self, user_id: UserId, *, limit: int, offset: int) -> list[Budget]:
        return self.active

    async def count(self, user_id: UserId) -> int:
        return len(self.active)

    async def list_active(self, user_id: UserId) -> list[Budget]:
        return self.active

    async def update(
        self,
        budget_id: BudgetId,
        user_id: UserId,
        *,
        name: str | None = None,
        amount: Decimal | None = None,
    ) -> Budget | None:
        if self.budget is None:
            return None
        self.budget = self.budget.model_copy(
            update={
                k: v
                for k, v in {"name": name, "amount": amount}.items()
                if v is not None
            }
        )
        return self.budget

    async def delete(self, budget_id: BudgetId, user_id: UserId) -> Budget | None:
        deleted = self.budget
        self.budget = None
        return deleted


REF = date(2024, 12, 15)


class TestGetBudget:
    async def test_raises_when_missing(self) -> None:
        service = BudgetService(FakeBudgetRepository(budget=None), FakeSpending(Decimal("0")))
        with pytest.raises(BudgetNotFoundError):
            await service.get_budget("missing", "u1")


class TestGetBudgetStatus:
    async def test_computes_spent_remaining_percentage(self) -> None:
        service = BudgetService(
            FakeBudgetRepository(budget=_budget(amount=Decimal("1000"))),
            FakeSpending(Decimal("250")),
        )

        status = await service.get_budget_status("bud-1", "u1", as_of=REF)

        assert status.spent == Decimal("250")
        assert status.remaining == Decimal("750")
        assert status.percentage == 25.0
        assert status.alert_triggered is False

    async def test_alert_triggers_at_or_above_threshold(self) -> None:
        service = BudgetService(
            FakeBudgetRepository(budget=_budget(amount=Decimal("1000"), alert_threshold=Decimal("80"))),
            FakeSpending(Decimal("800")),
        )

        status = await service.get_budget_status("bud-1", "u1", as_of=REF)

        assert status.percentage == 80.0
        assert status.alert_triggered is True

    async def test_disabled_alerts_never_trigger(self) -> None:
        service = BudgetService(
            FakeBudgetRepository(budget=_budget(amount=Decimal("1000"), alert_enabled=False)),
            FakeSpending(Decimal("5000")),
        )

        status = await service.get_budget_status("bud-1", "u1", as_of=REF)

        assert status.alert_triggered is False


class TestGetActiveAlerts:
    async def test_returns_only_triggered(self) -> None:
        over = _budget(amount=Decimal("100"))  # spending 90 -> 90% -> alert
        repo = FakeBudgetRepository(active=[over])
        service = BudgetService(repo, FakeSpending(Decimal("90")))

        alerts = await service.get_active_alerts("u1", as_of=REF)

        assert len(alerts) == 1
        assert alerts[0].alert_triggered is True

    async def test_empty_when_none_triggered(self) -> None:
        repo = FakeBudgetRepository(active=[_budget(amount=Decimal("1000"))])
        service = BudgetService(repo, FakeSpending(Decimal("10")))

        alerts = await service.get_active_alerts("u1", as_of=REF)

        assert alerts == []


class TestUpdateBudget:
    async def test_changes_amount(self) -> None:
        repo = FakeBudgetRepository(budget=_budget(amount=Decimal("1000")))
        service = BudgetService(repo, FakeSpending(Decimal("0")))

        updated = await service.update_budget("bud-1", "u1", amount=Decimal("2000"))

        assert updated.amount == Decimal("2000")
        assert updated.name == "Comida"  # unchanged

    async def test_raises_when_missing(self) -> None:
        service = BudgetService(FakeBudgetRepository(budget=None), FakeSpending(Decimal("0")))
        with pytest.raises(BudgetNotFoundError):
            await service.update_budget("missing", "u1", amount=Decimal("2000"))


class TestDeleteBudget:
    async def test_deletes(self) -> None:
        repo = FakeBudgetRepository(budget=_budget())
        service = BudgetService(repo, FakeSpending(Decimal("0")))

        deleted = await service.delete_budget("bud-1", "u1")

        assert deleted.name == "Comida"
        assert repo.budget is None

    async def test_raises_when_missing(self) -> None:
        service = BudgetService(FakeBudgetRepository(budget=None), FakeSpending(Decimal("0")))
        with pytest.raises(BudgetNotFoundError):
            await service.delete_budget("missing", "u1")


class TestResolveBudget:
    async def test_matches_by_category(self) -> None:
        repo = FakeBudgetRepository(active=[_budget()])  # category RESTAURANTES
        service = BudgetService(repo, FakeSpending(Decimal("0")))

        found = await service.resolve_budget("restaurantes", "u1")

        assert found is not None and found.id == "bud-1"

    async def test_matches_by_name_fuzzy(self) -> None:
        repo = FakeBudgetRepository(active=[_budget()])  # name "Comida"
        service = BudgetService(repo, FakeSpending(Decimal("0")))

        found = await service.resolve_budget("comida", "u1")

        assert found is not None and found.id == "bud-1"

    async def test_returns_none_when_no_match(self) -> None:
        repo = FakeBudgetRepository(active=[_budget()])
        service = BudgetService(repo, FakeSpending(Decimal("0")))

        assert await service.resolve_budget("gimnasio", "u1") is None
