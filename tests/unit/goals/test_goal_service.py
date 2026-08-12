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
    def __init__(
        self,
        sums: dict[str, Decimal] | None = None,
        contributions: list[tuple[Decimal, date]] | None = None,
        for_goal: list[GoalContribution] | None = None,
        in_period: list[GoalContribution] | None = None,
    ) -> None:
        self.created: list[tuple[str, str, Decimal, date]] = []
        self.deleted: list[str] = []
        self._sums = sums or {}
        # Dated (amount, date) pairs used by ``sum_in_period`` to sum in-range.
        self._contributions = contributions or []
        # Seeded rows returned verbatim by ``list_for_goal``.
        self._for_goal = for_goal or []
        # Seeded rows returned verbatim by ``list_in_period`` (already newest-first).
        self._in_period = in_period or []

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

    async def sum_in_period(self, user_id: UserId, start: date, end: date) -> Decimal:
        return sum(
            (amount for amount, day in self._contributions if start <= day <= end),
            start=Decimal("0"),
        )

    async def list_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[GoalContribution]:
        return [
            c for c in self._in_period if period_start <= c.contribution_date <= period_end
        ]

    async def list_for_goal(
        self, user_id: UserId, goal_id: GoalId
    ) -> list[GoalContribution]:
        return list(self._for_goal)

    async def delete(self, contribution_id: str, user_id: UserId) -> None:
        self.deleted.append(contribution_id)
        # Drop from the seeded list so the service test observes a real removal.
        self._for_goal = [c for c in self._for_goal if c.id != contribution_id]


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


class TestContributedInPeriod:
    async def test_sums_only_in_range_contributions(self) -> None:
        # 200@may (before), 300@jun, 400@jul (in range), 500@aug (after).
        contribs = FakeGoalContributionRepository(
            contributions=[
                (Decimal("200"), date(2026, 5, 31)),
                (Decimal("300"), date(2026, 6, 15)),
                (Decimal("400"), date(2026, 7, 31)),
                (Decimal("500"), date(2026, 8, 1)),
            ]
        )
        service = _service(FakeGoalRepository(goal=_goal()), contribs)

        total = await service.contributed_in_period(
            "u1", date(2026, 6, 1), date(2026, 7, 31)
        )

        assert total == Decimal("700")  # 300 + 400; may/aug excluded

    async def test_returns_zero_when_no_contributions(self) -> None:
        service = _service(FakeGoalRepository(goal=_goal()))

        total = await service.contributed_in_period(
            "u1", date(2026, 6, 1), date(2026, 6, 30)
        )

        assert total == Decimal("0")


class TestListContributionsInPeriod:
    async def test_maps_goal_name_and_falls_back_for_deleted_goal(self) -> None:
        # Two contributions: one to the existing goal-1, one to a goal that was
        # since deleted (goal-gone) -> the latter falls back to "Meta".
        repo = FakeGoalRepository(goal=_goal())  # goal-1 named "Viaje a Japón"
        seeded = [
            _contribution("c2", Decimal("300"), date(2026, 6, 20), goal_id="goal-1"),
            _contribution("c1", Decimal("200"), date(2026, 6, 10), goal_id="goal-gone"),
        ]
        contribs = FakeGoalContributionRepository(in_period=seeded)
        service = _service(repo, contribs)

        views = await service.list_contributions_in_period(
            "u1", date(2026, 6, 1), date(2026, 6, 30)
        )

        assert [v.goal_name for v in views] == ["Viaje a Japón", "Meta"]
        assert [v.amount for v in views] == [Decimal("300"), Decimal("200")]
        # Newest-first order is preserved from the repository.
        assert views[0].contribution_date == date(2026, 6, 20)

    async def test_filters_by_period_window(self) -> None:
        repo = FakeGoalRepository(goal=_goal())
        seeded = [
            _contribution("c_jul", Decimal("400"), date(2026, 7, 5), goal_id="goal-1"),
            _contribution("c_jun", Decimal("300"), date(2026, 6, 15), goal_id="goal-1"),
            _contribution("c_may", Decimal("200"), date(2026, 5, 31), goal_id="goal-1"),
        ]
        contribs = FakeGoalContributionRepository(in_period=seeded)
        service = _service(repo, contribs)

        views = await service.list_contributions_in_period(
            "u1", date(2026, 6, 1), date(2026, 6, 30)
        )

        assert [v.amount for v in views] == [Decimal("300")]  # only June

    async def test_returns_empty_when_no_contributions(self) -> None:
        service = _service(FakeGoalRepository(goal=_goal()))

        views = await service.list_contributions_in_period(
            "u1", date(2026, 6, 1), date(2026, 6, 30)
        )

        assert views == []


class TestListContributions:
    async def test_returns_repository_list(self) -> None:
        seeded = [
            GoalContribution(
                id="c2", goal_id="goal-1", user_id="u1",
                amount=Decimal("300"), contribution_date=date(2026, 7, 2),
                created_at=datetime.now(UTC),
            ),
            GoalContribution(
                id="c1", goal_id="goal-1", user_id="u1",
                amount=Decimal("200"), contribution_date=date(2026, 6, 15),
                created_at=datetime.now(UTC),
            ),
        ]
        repo = FakeGoalRepository(goal=_goal())
        contribs = FakeGoalContributionRepository(for_goal=seeded)
        service = _service(repo, contribs)

        result = await service.list_contributions("goal-1", "u1")

        assert result == seeded

    async def test_raises_when_goal_missing(self) -> None:
        service = _service(FakeGoalRepository(goal=None))
        with pytest.raises(GoalNotFoundError):
            await service.list_contributions("missing", "u1")


def _contribution(
    cid: str, amount: Decimal, when: date, goal_id: str = "goal-1"
) -> GoalContribution:
    return GoalContribution(
        id=cid,
        goal_id=goal_id,
        user_id="u1",
        amount=amount,
        contribution_date=when,
        created_at=datetime.now(UTC),
    )


class TestRemoveContribution:
    async def test_deletes_match_and_decrements_current_amount(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("25000")))
        seeded = [_contribution("c1", Decimal("5000"), date(2026, 6, 15))]
        contribs = FakeGoalContributionRepository(for_goal=seeded)
        service = _service(repo, contribs)

        result = await service.remove_contribution("goal-1", "u1", Decimal("5000"))

        assert contribs.deleted == ["c1"]  # the matching contribution was removed
        assert contribs._for_goal == []  # and it's gone from the seeded list
        assert repo.updated_data["current_amount"] == "20000"  # 25000 - 5000
        assert result is not None and result.current_amount == Decimal("20000")

    async def test_returns_none_when_no_match(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("25000")))
        contribs = FakeGoalContributionRepository(
            for_goal=[_contribution("c1", Decimal("5000"), date(2026, 6, 15))]
        )
        service = _service(repo, contribs)

        result = await service.remove_contribution("goal-1", "u1", Decimal("9999"))

        assert result is None
        assert contribs.deleted == []  # nothing deleted
        assert repo.updated_data == {}  # goal untouched

    async def test_disambiguates_by_date_when_amounts_tie(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("25000")))
        # Two 5000 contributions on different dates (newest first, as the repo returns).
        seeded = [
            _contribution("c_jul", Decimal("5000"), date(2026, 7, 10)),
            _contribution("c_jun", Decimal("5000"), date(2026, 6, 10)),
        ]
        contribs = FakeGoalContributionRepository(for_goal=seeded)
        service = _service(repo, contribs)

        await service.remove_contribution(
            "goal-1", "u1", Decimal("5000"), date(2026, 6, 10)
        )

        assert contribs.deleted == ["c_jun"]  # the dated one, not the most recent

    async def test_picks_most_recent_when_amounts_tie_and_no_date(self) -> None:
        repo = FakeGoalRepository(goal=_goal(current=Decimal("25000")))
        seeded = [
            _contribution("c_jul", Decimal("5000"), date(2026, 7, 10)),
            _contribution("c_jun", Decimal("5000"), date(2026, 6, 10)),
        ]
        contribs = FakeGoalContributionRepository(for_goal=seeded)
        service = _service(repo, contribs)

        await service.remove_contribution("goal-1", "u1", Decimal("5000"))

        assert contribs.deleted == ["c_jul"]  # newest-first list -> most recent

    async def test_reopens_completed_goal_when_falls_below_target(self) -> None:
        repo = FakeGoalRepository(
            goal=_goal(
                status=GoalStatus.COMPLETED,
                current=Decimal("100000"),
                target=Decimal("100000"),
            )
        )
        contribs = FakeGoalContributionRepository(
            for_goal=[_contribution("c1", Decimal("10000"), date(2026, 6, 15))]
        )
        service = _service(repo, contribs)

        await service.remove_contribution("goal-1", "u1", Decimal("10000"))

        assert repo.updated_data["current_amount"] == "90000"
        assert repo.updated_data["status"] == "active"  # 90k < 100k -> reopened

    async def test_preserves_paused_status(self) -> None:
        repo = FakeGoalRepository(
            goal=_goal(
                status=GoalStatus.PAUSED, current=Decimal("50000"), target=Decimal("100000")
            )
        )
        contribs = FakeGoalContributionRepository(
            for_goal=[_contribution("c1", Decimal("10000"), date(2026, 6, 15))]
        )
        service = _service(repo, contribs)

        await service.remove_contribution("goal-1", "u1", Decimal("10000"))

        assert "status" not in repo.updated_data  # paused kept, not re-derived

    async def test_floors_current_amount_at_zero(self) -> None:
        repo = FakeGoalRepository(
            goal=_goal(current=Decimal("5000"), target=Decimal("100000"))
        )
        contribs = FakeGoalContributionRepository(
            for_goal=[_contribution("c1", Decimal("8000"), date(2026, 6, 15))]
        )
        service = _service(repo, contribs)

        await service.remove_contribution("goal-1", "u1", Decimal("8000"))

        assert repo.updated_data["current_amount"] == "0"  # 5k - 8k floored at 0

    async def test_raises_when_goal_missing(self) -> None:
        service = _service(FakeGoalRepository(goal=None))
        with pytest.raises(GoalNotFoundError):
            await service.remove_contribution("missing", "u1", Decimal("5000"))


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
