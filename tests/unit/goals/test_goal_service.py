"""Unit tests for the goal service (repository mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.core.exceptions import GoalNotFoundError
from app.shared.types import CurrencyType, GoalId, GoalStatus, GoalType, UserId
from app.src.goals.interfaces import (
    GoalContributionRepositoryABC,
    GoalRepositoryABC,
)
from app.src.goals.models import Goal, GoalContribution, GoalCreate
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


class FakeGoalContributionRepository(GoalContributionRepositoryABC):
    def __init__(self, sums: dict[str, Decimal] | None = None) -> None:
        self.created: list[tuple[str, str, Decimal, date]] = []
        self._sums = sums or {}

    async def create(
        self, goal_id: GoalId, user_id: UserId, amount: Decimal, contribution_date: date
    ) -> GoalContribution:
        self.created.append((goal_id, user_id, amount, contribution_date))
        return GoalContribution(
            id="c1",
            goal_id=goal_id,
            user_id=user_id,
            amount=amount,
            contribution_date=contribution_date,
            created_at=datetime.now(UTC),
        )

    async def sums_up_to(self, user_id: UserId, as_of: date) -> dict[str, Decimal]:
        return dict(self._sums)


REF = date(2025, 1, 1)


def _service(
    repo: FakeGoalRepository,
    contribs: FakeGoalContributionRepository | None = None,
) -> GoalService:
    return GoalService(repo, contribs or FakeGoalContributionRepository())


class TestGetGoal:
    async def test_raises_when_missing(self) -> None:
        service = _service(FakeGoalRepository(goal=None))
        with pytest.raises(GoalNotFoundError):
            await service.get_goal("missing", "u1")


class TestContribute:
    async def test_adds_amount(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("25000")))
        contribs = FakeGoalContributionRepository()
        service = _service(repo, contribs)

        result = await service.contribute("goal-1", "u1", Decimal("5000"))

        assert repo.updated_data["current_amount"] == "30000"
        assert "status" not in repo.updated_data  # not yet reached
        assert result.current_amount == Decimal("30000")

    async def test_inserts_a_dated_contribution(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("25000")))
        contribs = FakeGoalContributionRepository()
        service = _service(repo, contribs)

        await service.contribute("goal-1", "u1", Decimal("5000"), date(2026, 6, 15))

        assert contribs.created == [("goal-1", "u1", Decimal("5000"), date(2026, 6, 15))]

    async def test_defaults_contribution_date_to_today(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("25000")))
        contribs = FakeGoalContributionRepository()
        service = _service(repo, contribs)

        await service.contribute("goal-1", "u1", Decimal("5000"))

        _goal_id, _user, _amount, when = contribs.created[0]
        assert when == datetime.now(UTC).date()

    async def test_completes_when_target_reached(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("95000")))
        service = _service(repo)

        result = await service.contribute("goal-1", "u1", Decimal("10000"))

        assert repo.updated_data["status"] == "completed"
        assert result.status == GoalStatus.COMPLETED

    async def test_can_contribute_to_completed_goal(self) -> None:
        # A completed goal still accepts contributions (save beyond target, or
        # backfill dated history) — it's not locked.
        repo = FakeGoalRepository(
            goal=_goal(status=GoalStatus.COMPLETED, current=Decimal("500000"))
        )
        contribs = FakeGoalContributionRepository()
        service = _service(repo, contribs)

        await service.contribute("goal-1", "u1", Decimal("100"))

        assert len(contribs.created) == 1  # contribution recorded, not rejected


class TestUpdateGoal:
    async def test_raising_target_reopens_completed_goal(self) -> None:
        repo = FakeGoalRepository(
            goal=_goal(
                status=GoalStatus.COMPLETED,
                current=Decimal("500000"),
                target=Decimal("500000"),
            )
        )
        service = _service(repo)

        await service.update_goal("goal-1", "u1", target_amount=Decimal("15000000"))

        assert repo.updated_data["status"] == "active"  # 500k < 15M → reopened

    async def test_name_only_leaves_status_untouched(self) -> None:
        repo = FakeGoalRepository(goal=_goal())
        service = _service(repo)

        await service.update_goal("goal-1", "u1", name="Fondo grande")

        assert repo.updated_data["name"] == "Fondo grande"
        assert "status" not in repo.updated_data  # status only changes with target


class TestListGoalsCumulative:
    async def test_as_of_returns_cumulative_up_to_month(self) -> None:
        # Contributions 200@jun, 300@jul, 100@aug -> cumulative end-June=200,
        # end-July=500, end-Aug=600. The cached running total is ignored.
        goal = _goal(current=Decimal("600"), target=Decimal("1000"))
        repo = FakeGoalRepository(goal=goal)

        cases = {
            date(2026, 6, 30): Decimal("200"),
            date(2026, 7, 31): Decimal("500"),
            date(2026, 8, 31): Decimal("600"),
        }
        for as_of, expected in cases.items():
            contribs = FakeGoalContributionRepository(sums={"goal-1": expected})
            service = _service(repo, contribs)

            items, total = await service.list_goals(
                "u1", page=1, page_size=20, as_of=as_of
            )

            assert total == 1
            assert items[0].current_amount == expected
            assert items[0].status == GoalStatus.ACTIVE  # 600 < 1000

    async def test_as_of_marks_completed_only_when_target_reached(self) -> None:
        repo = FakeGoalRepository(goal=_goal(target=Decimal("1000")))
        contribs = FakeGoalContributionRepository(sums={"goal-1": Decimal("1000")})
        service = _service(repo, contribs)

        items, _ = await service.list_goals("u1", page=1, page_size=20, as_of=date(2026, 8, 31))

        assert items[0].current_amount == Decimal("1000")
        assert items[0].status == GoalStatus.COMPLETED

    async def test_goal_with_no_contributions_shows_zero(self) -> None:
        repo = FakeGoalRepository(goal=_goal())
        service = _service(repo, FakeGoalContributionRepository(sums={}))

        items, _ = await service.list_goals("u1", page=1, page_size=20, as_of=date(2026, 6, 30))

        assert items[0].current_amount == Decimal("0")

    async def test_without_as_of_returns_running_total(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("25000")))
        service = _service(repo, FakeGoalContributionRepository(sums={"goal-1": Decimal("1")}))

        items, _ = await service.list_goals("u1", page=1, page_size=20)

        assert items[0].current_amount == Decimal("25000")


class TestProgress:
    async def test_basic_progress_and_required_monthly(self) -> None:
        service = _service(FakeGoalRepository(goal=_goal()))

        progress = await service.get_progress("goal-1", "u1", as_of=REF)

        assert progress.percentage == 25.0
        assert progress.remaining == Decimal("75000")
        assert progress.is_completed is False
        assert progress.months_remaining == 11  # Jan -> Dec
        assert progress.required_monthly_contribution == Decimal("6818.18")
        assert progress.on_track is True

    async def test_completed_goal(self) -> None:
        service = _service(FakeGoalRepository(goal=_goal(current=Decimal("100000"))))

        progress = await service.get_progress("goal-1", "u1", as_of=REF)

        assert progress.is_completed is True
        assert progress.remaining == Decimal("0")
        assert progress.required_monthly_contribution == Decimal("0")
        assert progress.on_track is True

    async def test_passed_deadline_not_on_track(self) -> None:
        service = _service(
            FakeGoalRepository(goal=_goal(target_date=date(2024, 12, 31)))
        )

        progress = await service.get_progress("goal-1", "u1", as_of=REF)

        assert progress.months_remaining == 0
        assert progress.required_monthly_contribution == Decimal("75000")  # lump sum
        assert progress.on_track is False

    async def test_no_deadline_has_no_required_monthly(self) -> None:
        service = _service(FakeGoalRepository(goal=_goal(target_date=None)))

        progress = await service.get_progress("goal-1", "u1", as_of=REF)

        assert progress.months_remaining is None
        assert progress.required_monthly_contribution is None
        assert progress.on_track is True
