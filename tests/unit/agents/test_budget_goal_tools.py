"""Unit tests for the budget and goal toolkits + the composite toolkit."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.agents.tools.budget_tools import BudgetToolkit
from app.agents.tools.composite_toolkit import CompositeToolkit
from app.agents.tools.goal_tools import GoalToolkit
from app.shared.types import (
    BudgetPeriod,
    CategoryType,
    CurrencyType,
    GoalStatus,
    GoalType,
)
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.budgets.models import Budget, BudgetCreate, BudgetStatus
from app.src.goals.interfaces import GoalServiceABC
from app.src.goals.models import Goal, GoalCreate, GoalProgress

NOW = datetime(2026, 7, 1, 10, 0, 0)


def _budget(**over: object) -> Budget:
    data: dict = {
        "id": "b1", "user_id": "u1", "name": "Comida", "amount": Decimal("3000"),
        "category": CategoryType.ALIMENTACION, "currency": CurrencyType.MXN,
        "period_type": BudgetPeriod.MONTHLY, "start_date": date(2026, 7, 1), "end_date": None,
        "alert_threshold": Decimal("80"), "alert_enabled": True, "is_active": True,
        "created_at": NOW,
    }
    data.update(over)
    return Budget(**data)


def _goal(**over: object) -> Goal:
    data: dict = {
        "id": "g1", "user_id": "u1", "name": "Viaje a Japón", "description": None,
        "goal_type": GoalType.SAVINGS, "target_amount": Decimal("100000"),
        "current_amount": Decimal("25000"), "currency": CurrencyType.MXN, "target_date": None,
        "monthly_contribution": None, "status": GoalStatus.ACTIVE, "priority": 1, "created_at": NOW,
    }
    data.update(over)
    return Goal(**data)


class FakeBudgetService(BudgetServiceABC):
    def __init__(self) -> None:
        self.created: list[tuple[BudgetCreate, str]] = []

    async def create_budget(self, budget: BudgetCreate, user_id: str) -> Budget:
        self.created.append((budget, user_id))
        return _budget(name=budget.name, amount=budget.amount, category=budget.category)

    async def list_budgets(self, user_id: str, *, page: int, page_size: int) -> tuple[list[Budget], int]:
        return [_budget()], 1

    async def get_budget_status(self, budget_id: str, user_id: str, as_of: date | None = None) -> BudgetStatus:
        return BudgetStatus(
            budget=_budget(), period_start=date(2026, 7, 1), period_end=date(2026, 7, 31),
            spent=Decimal("3200"), remaining=Decimal("-200"), percentage=106.0, alert_triggered=True,
        )

    async def get_budget(self, budget_id: str, user_id: str) -> Budget:
        return _budget()

    async def get_active_alerts(self, user_id: str, as_of: date | None = None) -> list[BudgetStatus]:
        return []

    async def get_all_status(self, user_id: str, as_of: date | None = None) -> list[BudgetStatus]:
        return []

    async def update_budget(
        self,
        budget_id: str,
        user_id: str,
        *,
        name: str | None = None,
        amount: Decimal | None = None,
    ) -> Budget:
        self.updated: dict[str, object] = {"id": budget_id, "name": name, "amount": amount}
        return _budget(
            **{k: v for k, v in {"name": name, "amount": amount}.items() if v is not None}
        )

    async def delete_budget(self, budget_id: str, user_id: str) -> Budget:
        self.deleted: str = budget_id
        return _budget()

    async def resolve_budget(self, reference: str, user_id: str) -> Budget | None:
        target = reference.lower()
        budget = _budget()
        if target in (budget.name.lower(), budget.category or ""):
            return budget
        return None


class FakeGoalService(GoalServiceABC):
    def __init__(self, goals: list[Goal] | None = None) -> None:
        self.created: list[tuple[GoalCreate, str]] = []
        self.contributions: list[tuple[str, str, Decimal]] = []
        self.deleted: list[tuple[str, str]] = []
        self._goals = goals if goals is not None else [_goal()]

    async def create_goal(self, goal: GoalCreate, user_id: str) -> Goal:
        self.created.append((goal, user_id))
        return _goal(name=goal.name, target_amount=goal.target_amount)

    async def list_goals(self, user_id: str, *, page: int, page_size: int) -> tuple[list[Goal], int]:
        return list(self._goals), len(self._goals)

    async def contribute(self, goal_id: str, user_id: str, amount: Decimal) -> Goal:
        self.contributions.append((goal_id, user_id, amount))
        return _goal(id=goal_id, current_amount=Decimal("25000") + amount)

    async def delete_goal(self, goal_id: str, user_id: str) -> Goal:
        self.deleted.append((goal_id, user_id))
        return _goal(id=goal_id)

    async def get_goal(self, goal_id: str, user_id: str) -> Goal:
        return _goal()

    async def get_progress(self, goal_id: str, user_id: str, as_of: date | None = None) -> GoalProgress:
        return GoalProgress(
            goal=_goal(), percentage=25.0, remaining=Decimal("75000"),
            is_completed=False, months_remaining=None,
            required_monthly_contribution=None, on_track=True,
        )


class TestBudgetToolkit:
    async def test_create_budget_passes_user_id_from_dispatch(self) -> None:
        service = FakeBudgetService()
        toolkit = BudgetToolkit(service)

        result = await toolkit.dispatch(
            "create_budget",
            {"name": "Comida", "amount": 3000, "category": "alimentacion", "user_id": "HACKER"},
            "u1",
        )

        budget, user_id = service.created[0]
        assert user_id == "u1"  # from dispatch, NOT the "HACKER" in args
        assert budget.name == "Comida"
        assert budget.category == CategoryType.ALIMENTACION
        assert "✅" in result

    async def test_query_budgets_formats_status(self) -> None:
        result = await BudgetToolkit(FakeBudgetService()).dispatch("query_budgets", {}, "u1")

        assert "Comida" in result
        assert "3200" in result and "3000" in result
        assert "106%" in result

    async def test_unknown_tool_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown budget tool"):
            await BudgetToolkit(FakeBudgetService()).dispatch("nope", {}, "u1")

    async def test_update_budget_resolves_by_category_and_changes_amount(self) -> None:
        service = FakeBudgetService()
        result = await BudgetToolkit(service).dispatch(
            "update_budget", {"reference": "alimentacion", "new_amount": 8000}, "u1"
        )
        assert service.updated["amount"] == Decimal("8000")
        assert "8000" in result and "✏️" in result

    async def test_update_budget_no_fields_asks(self) -> None:
        service = FakeBudgetService()
        result = await BudgetToolkit(service).dispatch(
            "update_budget", {"reference": "comida"}, "u1"
        )
        assert not hasattr(service, "updated")
        assert "¿qué quieres cambiar" in result.lower()

    async def test_update_unknown_budget_returns_message(self) -> None:
        service = FakeBudgetService()
        result = await BudgetToolkit(service).dispatch(
            "update_budget", {"reference": "gimnasio", "new_amount": 100}, "u1"
        )
        assert not hasattr(service, "updated")
        assert "no encontré" in result.lower()

    async def test_delete_budget_resolves_and_deletes(self) -> None:
        service = FakeBudgetService()
        result = await BudgetToolkit(service).dispatch(
            "delete_budget", {"reference": "comida"}, "u1"
        )
        assert service.deleted == "b1"
        assert "eliminé" in result.lower()

    async def test_delete_unknown_budget_returns_message(self) -> None:
        service = FakeBudgetService()
        result = await BudgetToolkit(service).dispatch(
            "delete_budget", {"reference": "gimnasio"}, "u1"
        )
        assert not hasattr(service, "deleted")
        assert "no encontré" in result.lower()


class TestGoalToolkit:
    async def test_create_goal(self) -> None:
        service = FakeGoalService()
        result = await GoalToolkit(service).dispatch(
            "create_goal", {"name": "Viaje a Japón", "target_amount": 100000}, "u1"
        )
        assert service.created[0][1] == "u1"
        assert "✅" in result and "Viaje a Japón" in result

    async def test_contribute_resolves_goal_by_name(self) -> None:
        service = FakeGoalService(goals=[_goal(id="g9", name="Viaje a Japón")])
        result = await GoalToolkit(service).dispatch(
            "contribute_to_goal", {"goal_name": "japón", "amount": 5000}, "u1"
        )
        goal_id, user_id, amount = service.contributions[0]
        assert goal_id == "g9" and user_id == "u1" and amount == Decimal("5000")
        assert "30000" in result  # 25000 + 5000

    async def test_contribute_resolves_ignoring_filler_words(self) -> None:
        # "vacaciones de la playa" should resolve to "vacaciones playa".
        service = FakeGoalService(goals=[_goal(id="g5", name="vacaciones playa")])
        await GoalToolkit(service).dispatch(
            "contribute_to_goal",
            {"goal_name": "vacaciones de la playa", "amount": 10000},
            "u1",
        )
        goal_id, _user, amount = service.contributions[0]
        assert goal_id == "g5"
        assert amount == Decimal("10000")

    async def test_contribute_unknown_goal_returns_message(self) -> None:
        service = FakeGoalService(goals=[_goal(name="Casa")])
        result = await GoalToolkit(service).dispatch(
            "contribute_to_goal", {"goal_name": "Moto", "amount": 100}, "u1"
        )
        assert not service.contributions
        assert "no encontré" in result.lower()

    async def test_query_goals_formats_progress(self) -> None:
        result = await GoalToolkit(FakeGoalService()).dispatch("query_goals", {}, "u1")
        assert "Viaje a Japón" in result and "25%" in result

    async def test_delete_goal_resolves_and_deletes(self) -> None:
        service = FakeGoalService(goals=[_goal(id="g7", name="vacaciones playa")])
        result = await GoalToolkit(service).dispatch(
            "delete_goal", {"goal_name": "vacaciones playa"}, "u1"
        )
        assert service.deleted[0] == ("g7", "u1")
        assert "eliminé" in result.lower()

    async def test_delete_unknown_goal_returns_message(self) -> None:
        service = FakeGoalService(goals=[_goal(name="Casa")])
        result = await GoalToolkit(service).dispatch(
            "delete_goal", {"goal_name": "Moto"}, "u1"
        )
        assert not service.deleted
        assert "no encontré" in result.lower()

    async def test_delete_duplicate_names_asks_which(self) -> None:
        service = FakeGoalService(
            goals=[
                _goal(id="a", name="vacaciones playa", target_amount=Decimal("50000")),
                _goal(id="b", name="vacaciones playa", target_amount=Decimal("10000")),
            ]
        )
        result = await GoalToolkit(service).dispatch(
            "delete_goal", {"goal_name": "vacaciones playa"}, "u1"
        )
        # Ambiguous: must NOT delete, and should ask which by target amount.
        assert not service.deleted
        assert "50000" in result and "10000" in result

    async def test_delete_disambiguates_by_target_amount(self) -> None:
        service = FakeGoalService(
            goals=[
                _goal(id="a", name="vacaciones playa", target_amount=Decimal("50000")),
                _goal(id="b", name="vacaciones playa", target_amount=Decimal("10000")),
            ]
        )
        await GoalToolkit(service).dispatch(
            "delete_goal",
            {"goal_name": "vacaciones playa", "goal_target_amount": 10000},
            "u1",
        )
        assert service.deleted[0] == ("b", "u1")


class TestCompositeToolkit:
    def test_merges_schemas(self) -> None:
        composite = CompositeToolkit([BudgetToolkit(FakeBudgetService()), GoalToolkit(FakeGoalService())])
        names = {s["function"]["name"] for s in composite.schemas}
        assert {
            "create_budget",
            "query_budgets",
            "create_goal",
            "query_goals",
            "contribute_to_goal",
            "delete_goal",
        } <= names

    async def test_routes_to_owning_toolkit(self) -> None:
        composite = CompositeToolkit([BudgetToolkit(FakeBudgetService()), GoalToolkit(FakeGoalService())])
        result = await composite.dispatch("query_goals", {}, "u1")
        assert "Viaje a Japón" in result

    async def test_unknown_tool_raises(self) -> None:
        composite = CompositeToolkit([BudgetToolkit(FakeBudgetService())])
        with pytest.raises(ValueError, match="Unknown tool"):
            await composite.dispatch("query_goals", {}, "u1")

    def test_duplicate_tool_name_raises(self) -> None:
        with pytest.raises(ValueError, match="Duplicate tool name"):
            CompositeToolkit([BudgetToolkit(FakeBudgetService()), BudgetToolkit(FakeBudgetService())])
