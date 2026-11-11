"""Unit tests for the goal-planning use cases of GoalService.

Contributions live in an in-memory ledger; the month provider is the real one, with
its RPC failing so the Python fallback computes the gross monthly totals.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.core.exceptions import (
    GoalNotFoundError,
    InvalidAmountError,
    InvalidPlanPeriodError,
)
from app.shared.types import (
    CurrencyType,
    GoalId,
    GoalPlanClearMode,
    GoalPlanKind,
    GoalPlanScope,
    GoalStatus,
    GoalType,
    UserId,
)
from app.src.goals.interfaces import GoalRepositoryABC
from app.src.goals.models import Goal, GoalCreate, GoalPlan
from app.src.goals.services.contribution_months_provider import ContributionMonthsProvider
from app.src.goals.services.goal_service import GoalService
from tests.conftest import BOGOTA_LATE_NIGHT
from tests.fakes import FakeProfileService, InMemoryContributionLedger, InMemoryGoalPlanRepository, RpcFailingDatabase

TODAY = date(2026, 6, 15)
D = Decimal


def _goal(
    goal_id: str = "g1",
    *,
    target: str = "10000",
    status: GoalStatus = GoalStatus.ACTIVE,
    created: datetime = datetime(2026, 1, 10, tzinfo=UTC),
    currency: CurrencyType = CurrencyType.MXN,
    name: str | None = None,
) -> Goal:
    return Goal(
        id=goal_id,
        user_id="u1",
        name=name or f"Meta {goal_id}",
        description=None,
        goal_type=GoalType.SAVINGS,
        target_amount=D(target),
        current_amount=D("0"),
        currency=currency,
        target_date=None,
        monthly_contribution=None,
        status=status,
        priority=1,
        created_at=created,
    )


class FakeGoalRepository(GoalRepositoryABC):
    def __init__(self, goals: list[Goal]) -> None:
        self.goals = goals

    async def create(self, goal: GoalCreate, user_id: UserId) -> Goal:
        raise NotImplementedError

    async def get_by_id(self, goal_id: GoalId, user_id: UserId) -> Goal | None:
        return next((g for g in self.goals if g.id == goal_id and g.user_id == user_id), None)

    async def list_page(self, user_id: UserId, *, limit: int, offset: int) -> list[Goal]:
        return self.goals[offset : offset + limit]

    async def count(self, user_id: UserId) -> int:
        return len(self.goals)

    async def update(self, goal_id: GoalId, user_id: UserId, data: dict[str, Any]) -> Goal:
        raise NotImplementedError

    async def delete(self, goal_id: GoalId, user_id: UserId) -> None:
        raise NotImplementedError


def _plan(
    kind: GoalPlanKind, month: date, amount: str, goal_id: str = "g1"
) -> GoalPlan:
    return GoalPlan(
        id=f"{goal_id}-{kind}-{month}",
        goal_id=goal_id,
        user_id="u1",
        month=month,
        planned_amount=D(amount),
        kind=kind,
    )


def _recurring(month: date, amount: str, goal_id: str = "g1") -> GoalPlan:
    return _plan(GoalPlanKind.RECURRING, month, amount, goal_id)


def _setup(
    goals: list[Goal],
    plans: list[GoalPlan] | None = None,
) -> tuple[GoalService, InMemoryContributionLedger, InMemoryGoalPlanRepository]:
    ledger = InMemoryContributionLedger()
    plan_repo = InMemoryGoalPlanRepository(plans)
    provider = ContributionMonthsProvider(RpcFailingDatabase(), ledger)  # type: ignore[arg-type]
    service = GoalService(
        FakeGoalRepository(goals), ledger, plan_repo, provider, FakeProfileService()  # type: ignore[arg-type]
    )
    return service, ledger, plan_repo


JUNE = (date(2026, 6, 1), date(2026, 6, 30))


class TestPlanStatusGrossVsNet:
    async def test_withdrawals_do_not_reduce_what_was_contributed(self) -> None:
        service, ledger, _ = _setup([_goal()], [_recurring(date(2026, 1, 1), "2000")])
        ledger.add("g1", D("1000"), date(2026, 5, 20))  # before June: opening balance
        ledger.add("g1", D("1500"), date(2026, 6, 3))
        ledger.add("g1", D("-500"), date(2026, 6, 20))

        [status] = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert status.contributed_gross == D("1500")  # NOT the net 1000
        assert status.withdrawn == D("500")
        assert status.planned == D("2000")
        assert status.remaining == D("500")  # 2000 - gross 1500
        assert status.percentage == 75.0
        assert status.is_met is False
        assert status.month == date(2026, 6, 1)

    async def test_met_when_gross_reaches_the_plan(self) -> None:
        service, ledger, _ = _setup([_goal()], [_recurring(date(2026, 1, 1), "2000")])
        ledger.add("g1", D("1500"), date(2026, 6, 3))
        ledger.add("g1", D("800"), date(2026, 6, 10))
        ledger.add("g1", D("-300"), date(2026, 6, 20))

        [status] = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert status.contributed_gross == D("2300")
        assert status.remaining == D("0")
        assert status.is_met is True

    async def test_exact_decimal_arithmetic(self) -> None:
        service, ledger, _ = _setup([_goal()], [_recurring(date(2026, 1, 1), "500.55")])
        ledger.add("g1", D("100.10"), date(2026, 6, 2))
        ledger.add("g1", D("200.20"), date(2026, 6, 9))

        [status] = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert status.contributed_gross == D("300.30")
        assert status.remaining == D("200.25")


class TestPlanStatusCap:
    async def test_plan_larger_than_what_was_missing_is_capped_in_remaining(self) -> None:
        service, ledger, _ = _setup([_goal(target="10000")], [_recurring(date(2026, 1, 1), "2000")])
        ledger.add("g1", D("9500"), date(2026, 5, 1))

        [status] = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert status.planned == D("2000")  # accepted as planned
        assert status.effective_planned == D("500")  # only 500 was missing
        assert status.remaining == D("500")
        assert status.goal_completed is False

    async def test_goal_completes_within_the_month(self) -> None:
        service, ledger, _ = _setup([_goal(target="10000")], [_recurring(date(2026, 1, 1), "2000")])
        ledger.add("g1", D("9500"), date(2026, 5, 1))
        ledger.add("g1", D("500"), date(2026, 6, 5))

        [status] = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert status.is_met is True
        assert status.percentage == 100.0
        assert status.goal_completed is True

    async def test_goal_full_at_month_start_without_contributions_is_left_out(self) -> None:
        service, ledger, _ = _setup([_goal(target="10000")], [_recurring(date(2026, 1, 1), "2000")])
        ledger.add("g1", D("10000"), date(2026, 5, 1))

        assert await service.get_plan_status("u1", *JUNE, today=TODAY) == []

    async def test_goal_completed_later_still_shows_in_the_month_it_was_incomplete(self) -> None:
        # Status is COMPLETED today, but in August the goal was still far from its target.
        goal = _goal(target="1000000", status=GoalStatus.COMPLETED)
        service, ledger, _ = _setup([goal], [_recurring(date(2026, 1, 1), "300000")])
        ledger.add("g1", D("100000"), date(2026, 7, 10))
        ledger.add("g1", D("900000"), date(2026, 10, 5))  # completed in October

        [status] = await service.get_plan_status(
            "u1", date(2026, 8, 1), date(2026, 8, 31), today=date(2026, 11, 9)
        )

        assert status.planned == D("300000")
        assert status.contributed_gross == D("0")
        assert status.is_met is False
        assert status.remaining == D("300000")

    async def test_goal_full_at_month_start_with_a_contribution_has_nothing_remaining(self) -> None:
        service, ledger, _ = _setup([_goal(target="10000")], [_recurring(date(2026, 1, 1), "2000")])
        ledger.add("g1", D("10000"), date(2026, 5, 1))
        ledger.add("g1", D("50"), date(2026, 6, 2))

        [status] = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert status.effective_planned == D("0")
        assert status.remaining == D("0")
        assert status.is_met is True


class TestPlanStatusInclusion:
    async def test_completed_goal_with_a_contribution_is_included(self) -> None:
        goal = _goal(status=GoalStatus.COMPLETED, target="1000")
        service, ledger, _ = _setup([goal], [_recurring(date(2026, 1, 1), "500")])
        ledger.add("g1", D("800"), date(2026, 5, 1))
        ledger.add("g1", D("200"), date(2026, 6, 4))

        statuses = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert [s.goal_id for s in statuses] == ["g1"]
        assert statuses[0].goal_completed is True

    async def test_completed_goal_without_contributions_is_left_out(self) -> None:
        goal = _goal(status=GoalStatus.COMPLETED, target="1000")
        service, ledger, _ = _setup([goal], [_recurring(date(2026, 1, 1), "500")])
        ledger.add("g1", D("1000"), date(2026, 5, 1))

        assert await service.get_plan_status("u1", *JUNE, today=TODAY) == []

    @pytest.mark.parametrize("status", [GoalStatus.PAUSED, GoalStatus.CANCELLED])
    async def test_paused_and_cancelled_are_left_out_of_current_and_future_months(
        self, status: GoalStatus
    ) -> None:
        service, _, _ = _setup([_goal(status=status)], [_recurring(date(2026, 1, 1), "500")])

        assert await service.get_plan_status("u1", *JUNE, today=TODAY) == []
        assert await service.get_plan_status("u1", date(2026, 9, 1), date(2026, 9, 30), today=TODAY) == []

    @pytest.mark.parametrize("status", [GoalStatus.PAUSED, GoalStatus.CANCELLED])
    async def test_paused_and_cancelled_keep_their_plans_in_past_months(
        self, status: GoalStatus
    ) -> None:
        service, _, _ = _setup([_goal(status=status)], [_recurring(date(2026, 1, 1), "500")])

        statuses = await service.get_plan_status(
            "u1", date(2026, 3, 1), date(2026, 3, 31), today=TODAY
        )

        assert [s.planned for s in statuses] == [D("500")]

    async def test_goal_without_a_plan_is_left_out(self) -> None:
        service, ledger, _ = _setup([_goal()])
        ledger.add("g1", D("700"), date(2026, 6, 4))

        assert await service.get_plan_status("u1", *JUNE, today=TODAY) == []

    async def test_goal_planning_zero_is_left_out(self) -> None:
        plans = [_recurring(date(2026, 1, 1), "500"), _plan(GoalPlanKind.OVERRIDE, date(2026, 6, 1), "0")]
        service, _, _ = _setup([_goal()], plans)

        assert await service.get_plan_status("u1", *JUNE, today=TODAY) == []

    async def test_month_before_the_goal_existed_has_no_plan(self) -> None:
        service, _, _ = _setup([_goal()], [_recurring(date(2025, 1, 1), "500")])

        assert await service.get_plan_status("u1", date(2025, 12, 1), date(2025, 12, 31), today=TODAY) == []

    async def test_several_goals_each_with_their_own_plan_and_currency(self) -> None:
        goals = [
            _goal("g1"),
            _goal("g2", currency=CurrencyType.USD),
            _goal("g3"),  # no plan
        ]
        plans = [
            _recurring(date(2026, 1, 1), "500", "g1"),
            _recurring(date(2026, 1, 1), "100", "g2"),
        ]
        service, ledger, _ = _setup(goals, plans)
        ledger.add("g1", D("200"), date(2026, 6, 2))
        ledger.add("g2", D("100"), date(2026, 6, 3))
        ledger.add("g3", D("999"), date(2026, 6, 3))

        statuses = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert [(s.goal_id, s.currency, s.contributed_gross) for s in statuses] == [
            ("g1", CurrencyType.MXN, D("200")),
            ("g2", CurrencyType.USD, D("100")),
        ]
        assert statuses[1].is_met is True


class TestPlanStatusMonthLimits:
    async def test_only_contributions_inside_the_month_count(self) -> None:
        service, ledger, _ = _setup([_goal()], [_recurring(date(2026, 1, 1), "5000")])
        ledger.add("g1", D("10"), date(2026, 5, 31))  # last day of May
        ledger.add("g1", D("20"), date(2026, 6, 1))  # first day of June
        ledger.add("g1", D("40"), date(2026, 6, 30))  # last day of June
        ledger.add("g1", D("80"), date(2026, 7, 1))  # first day of July

        [status] = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert status.contributed_gross == D("60")

    async def test_end_of_month_balance_counts_earlier_months_only_as_opening(self) -> None:
        # 9000 before June caps the plan at the 1000 still missing.
        service, ledger, _ = _setup([_goal(target="10000")], [_recurring(date(2026, 1, 1), "5000")])
        ledger.add("g1", D("9000"), date(2026, 5, 31))
        ledger.add("g1", D("5000"), date(2026, 7, 1))  # next month: not the opening of June

        [status] = await service.get_plan_status("u1", *JUNE, today=TODAY)

        assert status.effective_planned == D("1000")

    async def test_period_spanning_two_months_is_rejected(self) -> None:
        service, _, _ = _setup([_goal()])

        with pytest.raises(InvalidPlanPeriodError) as error:
            await service.get_plan_status("u1", date(2026, 6, 1), date(2026, 7, 31), today=TODAY)
        assert error.value.details["reason"] == "el período debe estar dentro de un solo mes"

    async def test_future_month_resolves_from_the_recurring(self) -> None:
        service, _, _ = _setup([_goal()], [_recurring(date(2026, 1, 1), "500")])

        [status] = await service.get_plan_status(
            "u1", date(2026, 9, 1), date(2026, 9, 30), today=TODAY
        )

        assert status.planned == D("500")
        assert status.contributed_gross == D("0")
        assert status.remaining == D("500")


class TestMonthlyHistory:
    async def test_six_months_before_plus_the_chosen_month(self) -> None:
        goal = _goal(created=datetime(2025, 6, 1, tzinfo=UTC))
        plans = [
            _recurring(date(2025, 6, 1), "500"),
            _recurring(date(2026, 3, 1), "800"),
            _plan(GoalPlanKind.OVERRIDE, date(2026, 4, 1), "0"),
        ]
        service, ledger, _ = _setup([goal], plans)
        ledger.add("g1", D("2000"), date(2025, 8, 10))  # before the window: opening
        ledger.add("g1", D("400"), date(2025, 12, 5))
        ledger.add("g1", D("-100"), date(2025, 12, 20))
        ledger.add("g1", D("900"), date(2026, 3, 2))

        lines = await service.get_monthly_history("u1", 6, today=TODAY)

        assert [line.month for line in lines] == [
            date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1),
            date(2026, 4, 1), date(2026, 5, 1), date(2026, 6, 1),
        ]  # fmt: skip
        assert [line.planned for line in lines] == [
            D("500"), D("500"), D("500"), D("800"), D("0"), D("800"), D("800"),
        ]  # fmt: skip
        dec, _jan, _feb, mar, *_ = lines
        assert (dec.saved, dec.withdrawn) == (D("400"), D("100"))
        assert dec.cumulative == D("2300")  # 2000 opening + 400 - 100
        assert mar.saved == D("900")
        assert lines[-1].cumulative == D("3200")

    async def test_future_months_only_appear_with_a_plan(self) -> None:
        planned = _goal("g1")
        unplanned = _goal("g2")
        service, _, _ = _setup([planned, unplanned], [_recurring(date(2026, 1, 1), "500", "g1")])

        lines = await service.get_monthly_history("u1", 2, date(2026, 8, 1), today=TODAY)

        by_goal = {
            gid: [line.month for line in lines if line.goal_id == gid] for gid in ("g1", "g2")
        }
        assert by_goal["g1"] == [date(2026, m, 1) for m in (6, 7, 8)]
        assert by_goal["g2"] == [date(2026, 6, 1)]  # up to today only, no plan ahead

    async def test_lines_are_ordered_by_goal_then_month(self) -> None:
        service, _, _ = _setup([_goal("g1"), _goal("g2")])

        lines = await service.get_monthly_history("u1", 1, today=TODAY)

        assert [(line.goal_id, line.month.month) for line in lines] == [
            ("g1", 5), ("g1", 6), ("g2", 5), ("g2", 6),
        ]  # fmt: skip

    async def test_unplanned_month_has_none_not_zero(self) -> None:
        service, ledger, _ = _setup([_goal()])
        ledger.add("g1", D("100"), date(2026, 6, 1))

        [*_, last] = await service.get_monthly_history("u1", 1, today=TODAY)

        assert last.planned is None
        assert last.saved == D("100")

    @pytest.mark.parametrize("months", [0, 25])
    async def test_months_out_of_range_is_rejected(self, months: int) -> None:
        service, _, _ = _setup([_goal()])

        with pytest.raises(InvalidPlanPeriodError):
            await service.get_monthly_history("u1", months, today=TODAY)


class TestSetPlan:
    async def test_solo_mes_writes_an_override_for_that_month_only(self) -> None:
        service, _, repo = _setup([_goal()], [_recurring(date(2026, 1, 1), "500")])

        result = await service.set_plan(
            "u1", "g1", D("900"), date(2026, 6, 17), GoalPlanScope.SOLO_MES
        )

        assert result == D("900")
        assert (("g1", date(2026, 6, 1), GoalPlanKind.OVERRIDE)) in repo.rows  # normalized to day 1
        assert repo.rows[("g1", date(2026, 6, 1), GoalPlanKind.OVERRIDE)].planned_amount == D("900")
        # next month falls back to the recurring
        [(_, plan)] = [(k, v) for k, v in repo.rows.items() if k[2] == GoalPlanKind.RECURRING]
        assert plan.planned_amount == D("500")

    async def test_desde_mes_writes_a_recurring_and_drops_that_months_override(self) -> None:
        plans = [
            _recurring(date(2026, 1, 1), "500"),
            _plan(GoalPlanKind.OVERRIDE, date(2026, 6, 1), "900"),
        ]
        service, _, repo = _setup([_goal()], plans)

        result = await service.set_plan(
            "u1", "g1", D("700"), date(2026, 6, 1), GoalPlanScope.DESDE_MES
        )

        assert result == D("700")  # the old override no longer shadows it
        assert ("g1", date(2026, 6, 1), GoalPlanKind.OVERRIDE) not in repo.rows
        # history untouched: the earlier recurring is still there
        assert repo.rows[("g1", date(2026, 1, 1), GoalPlanKind.RECURRING)].planned_amount == D("500")

    async def test_past_months_can_be_planned(self) -> None:
        service, _, _ = _setup([_goal()])

        result = await service.set_plan(
            "u1", "g1", D("300"), date(2026, 2, 1), GoalPlanScope.SOLO_MES
        )

        assert result == D("300")

    async def test_amount_is_rounded_to_cents(self) -> None:
        service, _, _ = _setup([_goal()])

        result = await service.set_plan(
            "u1", "g1", D("10.126"), date(2026, 6, 1), GoalPlanScope.SOLO_MES
        )

        assert result == D("10.13")

    async def test_zero_is_a_valid_plan(self) -> None:
        service, _, _ = _setup([_goal()])

        result = await service.set_plan(
            "u1", "g1", D("0"), date(2026, 6, 1), GoalPlanScope.SOLO_MES
        )

        assert result == D("0")

    @pytest.mark.parametrize("amount", [D("-1"), D("NaN"), D("Infinity"), D("10000000000")])
    async def test_invalid_amounts_are_rejected(self, amount: Decimal) -> None:
        service, _, repo = _setup([_goal()])

        with pytest.raises(InvalidAmountError):
            await service.set_plan("u1", "g1", amount, date(2026, 6, 1), GoalPlanScope.SOLO_MES)
        assert repo.rows == {}

    async def test_missing_goal_raises_and_writes_nothing(self) -> None:
        service, _, repo = _setup([_goal()])

        with pytest.raises(GoalNotFoundError):
            await service.set_plan("u1", "nope", D("1"), date(2026, 6, 1), GoalPlanScope.SOLO_MES)
        assert repo.rows == {}

    async def test_another_users_goal_is_not_found(self) -> None:
        service, _, repo = _setup([_goal()])

        with pytest.raises(GoalNotFoundError):
            await service.set_plan("u2", "g1", D("1"), date(2026, 6, 1), GoalPlanScope.SOLO_MES)
        assert repo.rows == {}

    async def test_month_before_the_goal_was_created_is_rejected(self) -> None:
        service, _, repo = _setup([_goal()])  # created 2026-01-10

        with pytest.raises(InvalidPlanPeriodError, match="antes de crear la meta"):
            await service.set_plan("u1", "g1", D("1"), date(2025, 12, 1), GoalPlanScope.DESDE_MES)
        assert repo.rows == {}

    async def test_goal_created_late_on_the_last_day_belongs_to_the_local_month(self) -> None:
        # 2026-10-31 23:30 Bogota == 2026-11-01T04:30Z: the goal was created in OCTOBER.
        goal = _goal(created=BOGOTA_LATE_NIGHT)
        service, ledger, repo = _setup([goal])

        result = await service.set_plan(
            "u1", "g1", D("300"), date(2026, 10, 1), GoalPlanScope.DESDE_MES
        )

        assert result == D("300")  # not None
        assert ("g1", date(2026, 10, 1), GoalPlanKind.RECURRING) in repo.rows
        lines = await service.get_monthly_history("u1", 1, today=date(2026, 10, 31))
        assert [(line.month, line.planned) for line in lines] == [(date(2026, 10, 1), D("300"))]

    async def test_desde_mes_replaces_plans_set_ahead(self) -> None:
        plans = [
            _recurring(date(2026, 1, 1), "500000"),
            _plan(GoalPlanKind.OVERRIDE, date(2026, 12, 1), "42"),
        ]
        service, _, repo = _setup([_goal()], plans)
        ahead = _recurring(date(2027, 1, 1), "900")
        repo.rows[("g1", ahead.month, ahead.kind)] = ahead

        await service.set_plan("u1", "g1", D("300000"), date(2026, 11, 1), GoalPlanScope.DESDE_MES)

        assert ("g1", date(2027, 1, 1), GoalPlanKind.RECURRING) not in repo.rows
        [january] = await service.get_plan_status(
            "u1", date(2027, 1, 1), date(2027, 1, 31), today=date(2026, 11, 9)
        )
        assert january.planned == D("300000")
        # a later override is a specific month: it survives
        assert ("g1", date(2026, 12, 1), GoalPlanKind.OVERRIDE) in repo.rows
        # earlier history untouched
        assert repo.rows[("g1", date(2026, 1, 1), GoalPlanKind.RECURRING)].planned_amount == D("500000")

    async def test_desde_mes_deletes_before_upserting(self) -> None:
        events: list[str] = []
        service, _, repo = _setup([_goal()], [_recurring(date(2026, 8, 1), "5")])
        original_delete, original_upsert = repo.delete, repo.upsert

        async def delete(*args: Any) -> None:
            events.append("delete")
            await original_delete(*args)

        async def upsert(*args: Any) -> GoalPlan:
            events.append("upsert")
            return await original_upsert(*args)

        repo.delete = delete  # type: ignore[method-assign]
        repo.upsert = upsert  # type: ignore[method-assign]

        await service.set_plan("u1", "g1", D("7"), date(2026, 6, 1), GoalPlanScope.DESDE_MES)

        assert events == ["delete", "upsert"]


class TestClearPlan:
    async def test_sin_plan_plans_zero_just_for_that_month(self) -> None:
        service, _, _ = _setup([_goal()], [_recurring(date(2026, 1, 1), "500")])

        result = await service.clear_plan("u1", "g1", date(2026, 6, 1), GoalPlanClearMode.SIN_PLAN)

        assert result == D("0")  # a planned 0, not "no plan"

    async def test_volver_al_general_drops_the_override(self) -> None:
        plans = [
            _recurring(date(2026, 1, 1), "500"),
            _plan(GoalPlanKind.OVERRIDE, date(2026, 6, 1), "900"),
        ]
        service, _, repo = _setup([_goal()], plans)

        result = await service.clear_plan(
            "u1", "g1", date(2026, 6, 20), GoalPlanClearMode.VOLVER_AL_GENERAL
        )

        assert result == D("500")
        assert ("g1", date(2026, 6, 1), GoalPlanKind.OVERRIDE) not in repo.rows

    async def test_volver_al_general_without_override_is_a_noop(self) -> None:
        service, _, _ = _setup([_goal()], [_recurring(date(2026, 1, 1), "500")])

        result = await service.clear_plan(
            "u1", "g1", date(2026, 6, 1), GoalPlanClearMode.VOLVER_AL_GENERAL
        )

        assert result == D("500")

    async def test_terminar_stops_planning_from_that_month_and_keeps_history(self) -> None:
        service, _, repo = _setup([_goal()], [_recurring(date(2026, 1, 1), "500")])

        result = await service.clear_plan("u1", "g1", date(2026, 6, 1), GoalPlanClearMode.TERMINAR)

        assert result == D("0")
        assert repo.rows[("g1", date(2026, 6, 1), GoalPlanKind.RECURRING)].planned_amount == D("0")
        assert repo.rows[("g1", date(2026, 1, 1), GoalPlanKind.RECURRING)].planned_amount == D("500")

    async def test_terminar_removes_everything_planned_from_that_month_on(self) -> None:
        plans = [
            _recurring(date(2026, 1, 1), "500000"),
            _plan(GoalPlanKind.OVERRIDE, date(2026, 11, 1), "1"),
            _plan(GoalPlanKind.OVERRIDE, date(2026, 12, 1), "2"),
            _plan(GoalPlanKind.OVERRIDE, date(2026, 5, 1), "3"),
        ]
        service, _, repo = _setup([_goal()], plans)
        ahead = _recurring(date(2027, 1, 1), "900")
        repo.rows[("g1", ahead.month, ahead.kind)] = ahead

        result = await service.clear_plan("u1", "g1", date(2026, 11, 1), GoalPlanClearMode.TERMINAR)

        assert result == D("0")
        assert ("g1", date(2027, 1, 1), GoalPlanKind.RECURRING) not in repo.rows
        assert ("g1", date(2026, 12, 1), GoalPlanKind.OVERRIDE) not in repo.rows
        assert ("g1", date(2026, 11, 1), GoalPlanKind.OVERRIDE) not in repo.rows
        assert ("g1", date(2026, 5, 1), GoalPlanKind.OVERRIDE) in repo.rows  # history kept
        # January stops resolving to the old 500k (or the 900): planning ended in November
        assert await service.get_plan_status(
            "u1", date(2027, 1, 1), date(2027, 1, 31), today=date(2026, 11, 9)
        ) == []

    async def test_month_before_the_goal_was_created_is_rejected(self) -> None:
        service, _, _ = _setup([_goal()])

        with pytest.raises(InvalidPlanPeriodError, match="antes de crear la meta"):
            await service.clear_plan("u1", "g1", date(2025, 12, 1), GoalPlanClearMode.SIN_PLAN)

    async def test_missing_goal_raises(self) -> None:
        service, _, _ = _setup([_goal()])

        with pytest.raises(GoalNotFoundError):
            await service.clear_plan("u1", "nope", date(2026, 6, 1), GoalPlanClearMode.SIN_PLAN)


class TestHistoryEffectivePlan:
    async def test_effective_plan_is_capped_at_what_was_missing_at_each_month_start(self) -> None:
        service, ledger, _ = _setup([_goal(target="10000")], [_recurring(date(2026, 1, 1), "2000")])
        ledger.add("g1", D("9500"), date(2026, 5, 10))

        lines = await service.get_monthly_history("u1", 2, today=TODAY)
        by_month = {line.month: line for line in lines}

        assert by_month[date(2026, 4, 1)].effective_planned == D("2000")  # 10000 still missing
        assert by_month[date(2026, 5, 1)].effective_planned == D("2000")  # started at 0
        assert by_month[date(2026, 6, 1)].effective_planned == D("500")  # 9500 held at the start
        assert by_month[date(2026, 6, 1)].planned == D("2000")  # the plan itself is untouched

    async def test_no_plan_means_no_effective_plan(self) -> None:
        service, _, _ = _setup([_goal()])

        [*_, last] = await service.get_monthly_history("u1", 1, today=TODAY)

        assert last.planned is None and last.effective_planned is None

    async def test_a_goal_already_full_has_zero_effective_plan(self) -> None:
        service, ledger, _ = _setup([_goal(target="1000")], [_recurring(date(2026, 1, 1), "300")])
        ledger.add("g1", D("1000"), date(2026, 4, 2))

        lines = await service.get_monthly_history("u1", 1, today=TODAY)

        assert [line.effective_planned for line in lines] == [D("0"), D("0")]

    async def test_months_out_of_range_reason_is_in_spanish(self) -> None:
        service, _, _ = _setup([_goal()])

        with pytest.raises(InvalidPlanPeriodError) as error:
            await service.get_monthly_history("u1", 0, today=TODAY)

        assert error.value.details["reason"] == "los meses deben estar entre 1 y 24"
        assert "inválido" in error.value.message


class TestFlowsInPeriod:
    async def test_gross_saved_and_withdrawn_with_inclusive_limits(self) -> None:
        service, ledger, _ = _setup([_goal("g1"), _goal("g2")])
        ledger.add("g1", D("100.10"), date(2026, 6, 1))
        ledger.add("g2", D("200.20"), date(2026, 6, 30))
        ledger.add("g1", D("-50.05"), date(2026, 6, 15))
        ledger.add("g1", D("999"), date(2026, 7, 1))  # outside
        ledger.add("g1", D("999"), date(2026, 5, 31))  # outside

        flows = await service.flows_in_period("u1", *JUNE)

        assert flows.saved == D("300.30")  # gross: the retiro does not net out
        assert flows.withdrawn == D("50.05")

    async def test_empty_period(self) -> None:
        service, _, _ = _setup([_goal()])

        flows = await service.flows_in_period("u1", *JUNE)

        assert (flows.saved, flows.withdrawn) == (D("0"), D("0"))

    async def test_monthly_flows_delegates_to_the_provider(self) -> None:
        service, ledger, _ = _setup([_goal()])
        ledger.add("g1", D("10"), date(2026, 5, 3))
        ledger.add("g1", D("20"), date(2026, 6, 3))

        rows = await service.monthly_flows("u1", date(2026, 5, 1), date(2026, 6, 30))

        assert [(r.month, r.saved) for r in rows] == [(date(2026, 5, 1), D("10")), (date(2026, 6, 1), D("20"))]
