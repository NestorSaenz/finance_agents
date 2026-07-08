"""Unit tests for the goal service (repository mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.core.exceptions import GoalAlreadyCompletedError, GoalNotFoundError
from app.shared.types import CurrencyType, GoalId, GoalStatus, GoalType, UserId
from app.src.goals.interfaces import GoalRepositoryABC
from app.src.goals.models import Goal, GoalCreate
from app.src.goals.services.goal_service import GoalService


def _goal(
    current: Decimal = Decimal("25000"),
    target: Decimal = Decimal("100000"),
    status: GoalStatus = GoalStatus.ACTIVE,
    target_date: date | None = date(2025, 12, 31),
) -> Goal:
    return Goal(
        id="goal-1",
        user_id="u1",
        name="Viaje a Japón",
        description=None,
        goal_type=GoalType.SAVINGS,
        target_amount=target,
        current_amount=current,
        currency=CurrencyType.MXN,
        target_date=target_date,
        monthly_contribution=None,
        status=status,
        priority=1,
        created_at=datetime.now(UTC),
    )


class FakeGoalRepository(GoalRepositoryABC):
    def __init__(self, goal: Goal | None = None) -> None:
        self.goal = goal
        self.updated_data: dict[str, Any] = {}
        self.deleted: str | None = None

    async def create(self, goal: GoalCreate, user_id: UserId) -> Goal:
        return _goal(current=goal.current_amount, target=goal.target_amount)

    async def get_by_id(self, goal_id: GoalId, user_id: UserId) -> Goal | None:
        return self.goal

    async def list_page(self, user_id: UserId, *, limit: int, offset: int) -> list[Goal]:
        return [self.goal] if self.goal else []

    async def count(self, user_id: UserId) -> int:
        return 1 if self.goal else 0

    async def update(self, goal_id: GoalId, user_id: UserId, data: dict[str, Any]) -> Goal:
        self.updated_data = data
        assert self.goal is not None
        return self.goal.model_copy(
            update={
                "current_amount": Decimal(str(data.get("current_amount", self.goal.current_amount))),
                "status": GoalStatus(data["status"]) if "status" in data else self.goal.status,
            }
        )

    async def delete(self, goal_id: GoalId, user_id: UserId) -> None:
        self.deleted = goal_id


REF = date(2025, 1, 1)


class TestGetGoal:
    async def test_raises_when_missing(self) -> None:
        service = GoalService(FakeGoalRepository(goal=None))
        with pytest.raises(GoalNotFoundError):
            await service.get_goal("missing", "u1")


class TestContribute:
    async def test_adds_amount(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("25000")))
        service = GoalService(repo)

        result = await service.contribute("goal-1", "u1", Decimal("5000"))

        assert repo.updated_data["current_amount"] == "30000"
        assert "status" not in repo.updated_data  # not yet reached
        assert result.current_amount == Decimal("30000")

    async def test_completes_when_target_reached(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("95000")))
        service = GoalService(repo)

        result = await service.contribute("goal-1", "u1", Decimal("10000"))

        assert repo.updated_data["status"] == "completed"
        assert result.status == GoalStatus.COMPLETED

    async def test_contributing_to_completed_goal_raises(self) -> None:
        repo = FakeGoalRepository(goal=_goal(status=GoalStatus.COMPLETED))
        service = GoalService(repo)
        with pytest.raises(GoalAlreadyCompletedError):
            await service.contribute("goal-1", "u1", Decimal("100"))


class TestProgress:
    async def test_basic_progress_and_required_monthly(self) -> None:
        service = GoalService(FakeGoalRepository(goal=_goal()))

        progress = await service.get_progress("goal-1", "u1", as_of=REF)

        assert progress.percentage == 25.0
        assert progress.remaining == Decimal("75000")
        assert progress.is_completed is False
        assert progress.months_remaining == 11  # Jan -> Dec
        assert progress.required_monthly_contribution == Decimal("6818.18")
        assert progress.on_track is True

    async def test_completed_goal(self) -> None:
        service = GoalService(FakeGoalRepository(goal=_goal(current=Decimal("100000"))))

        progress = await service.get_progress("goal-1", "u1", as_of=REF)

        assert progress.is_completed is True
        assert progress.remaining == Decimal("0")
        assert progress.required_monthly_contribution == Decimal("0")
        assert progress.on_track is True

    async def test_passed_deadline_not_on_track(self) -> None:
        service = GoalService(
            FakeGoalRepository(goal=_goal(target_date=date(2024, 12, 31)))
        )

        progress = await service.get_progress("goal-1", "u1", as_of=REF)

        assert progress.months_remaining == 0
        assert progress.required_monthly_contribution == Decimal("75000")  # lump sum
        assert progress.on_track is False

    async def test_no_deadline_has_no_required_monthly(self) -> None:
        service = GoalService(FakeGoalRepository(goal=_goal(target_date=None)))

        progress = await service.get_progress("goal-1", "u1", as_of=REF)

        assert progress.months_remaining is None
        assert progress.required_monthly_contribution is None
        assert progress.on_track is True
