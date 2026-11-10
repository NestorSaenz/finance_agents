"""Unit tests for the pure goal-planning helpers (resolve_plan and month math)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.shared.types import GoalPlanKind
from app.src.goals.models import GoalPlan
from app.src.goals.planning import (
    add_months,
    first_of_month,
    goal_created_month,
    last_of_month,
    month_key,
    month_range,
    resolve_plan,
)
from tests.conftest import BOGOTA_LATE_NIGHT

CREATED = date(2026, 1, 1)


def _plan(kind: GoalPlanKind, month: date, amount: str) -> GoalPlan:
    return GoalPlan(
        id=f"{kind}-{month}",
        goal_id="goal-1",
        user_id="u1",
        month=month,
        planned_amount=Decimal(amount),
        kind=kind,
    )


def _recurring(month: date, amount: str) -> GoalPlan:
    return _plan(GoalPlanKind.RECURRING, month, amount)


def _override(month: date, amount: str) -> GoalPlan:
    return _plan(GoalPlanKind.OVERRIDE, month, amount)


class TestResolvePlan:
    def test_no_rows_means_no_plan(self) -> None:
        assert resolve_plan([], date(2026, 3, 1), CREATED) is None

    def test_recurring_applies_from_its_month_onward(self) -> None:
        plans = [_recurring(date(2026, 2, 1), "500")]

        assert resolve_plan(plans, date(2026, 1, 1), CREATED) is None
        assert resolve_plan(plans, date(2026, 2, 1), CREATED) == Decimal("500")
        assert resolve_plan(plans, date(2026, 9, 1), CREATED) == Decimal("500")

    def test_override_beats_the_recurring_in_its_month_only(self) -> None:
        plans = [_recurring(date(2026, 2, 1), "500"), _override(date(2026, 4, 1), "900")]

        assert resolve_plan(plans, date(2026, 4, 1), CREATED) == Decimal("900")
        assert resolve_plan(plans, date(2026, 3, 1), CREATED) == Decimal("500")
        assert resolve_plan(plans, date(2026, 5, 1), CREATED) == Decimal("500")

    def test_override_alone_plans_only_that_month(self) -> None:
        plans = [_override(date(2026, 4, 1), "900")]

        assert resolve_plan(plans, date(2026, 4, 1), CREATED) == Decimal("900")
        assert resolve_plan(plans, date(2026, 5, 1), CREATED) is None

    def test_override_of_zero_is_a_planned_zero_not_no_plan(self) -> None:
        plans = [_recurring(date(2026, 2, 1), "500"), _override(date(2026, 4, 1), "0")]

        assert resolve_plan(plans, date(2026, 4, 1), CREATED) == Decimal("0")

    def test_latest_recurring_wins(self) -> None:
        plans = [
            _recurring(date(2026, 2, 1), "500"),
            _recurring(date(2026, 6, 1), "800"),
            _recurring(date(2026, 4, 1), "650"),
        ]

        assert resolve_plan(plans, date(2026, 5, 1), CREATED) == Decimal("650")
        assert resolve_plan(plans, date(2026, 6, 1), CREATED) == Decimal("800")
        assert resolve_plan(plans, date(2026, 12, 1), CREATED) == Decimal("800")

    def test_changing_the_recurring_does_not_rewrite_past_months(self) -> None:
        before = [_recurring(date(2026, 2, 1), "500")]
        after = [*before, _recurring(date(2026, 6, 1), "800")]

        for month in (date(2026, 2, 1), date(2026, 3, 1), date(2026, 5, 1)):
            assert resolve_plan(after, month, CREATED) == resolve_plan(before, month, CREATED)
        assert resolve_plan(after, date(2026, 6, 1), CREATED) == Decimal("800")

    def test_recurring_of_zero_stops_planning_from_that_month(self) -> None:
        plans = [_recurring(date(2026, 2, 1), "500"), _recurring(date(2026, 5, 1), "0")]

        assert resolve_plan(plans, date(2026, 4, 1), CREATED) == Decimal("500")
        assert resolve_plan(plans, date(2026, 5, 1), CREATED) == Decimal("0")
        assert resolve_plan(plans, date(2026, 8, 1), CREATED) == Decimal("0")

    def test_dropping_the_override_returns_to_the_general_plan(self) -> None:
        recurring = _recurring(date(2026, 2, 1), "500")
        with_override = [recurring, _override(date(2026, 4, 1), "900")]

        assert resolve_plan(with_override, date(2026, 4, 1), CREATED) == Decimal("900")
        assert resolve_plan([recurring], date(2026, 4, 1), CREATED) == Decimal("500")

    def test_no_plan_before_the_goal_was_created(self) -> None:
        created = date(2026, 3, 1)
        plans = [_recurring(date(2026, 1, 1), "500"), _override(date(2026, 2, 1), "700")]

        assert resolve_plan(plans, date(2026, 2, 1), created) is None
        assert resolve_plan(plans, date(2026, 3, 1), created) == Decimal("500")

    def test_any_day_of_the_month_resolves_like_its_first_day(self) -> None:
        plans = [_recurring(date(2026, 2, 1), "500")]

        assert resolve_plan(plans, date(2026, 2, 17), CREATED) == Decimal("500")


class TestMonthHelpers:
    def test_first_and_last_of_month(self) -> None:
        assert first_of_month(date(2026, 2, 17)) == date(2026, 2, 1)
        assert last_of_month(date(2026, 2, 17)) == date(2026, 2, 28)
        assert last_of_month(date(2028, 2, 1)) == date(2028, 2, 29)  # leap year

    @pytest.mark.parametrize(
        ("start", "count", "expected"),
        [
            (date(2026, 11, 1), 1, date(2026, 12, 1)),
            (date(2026, 12, 1), 1, date(2027, 1, 1)),
            (date(2026, 1, 1), -1, date(2025, 12, 1)),
            (date(2026, 3, 1), -6, date(2025, 9, 1)),
            (date(2026, 3, 1), 0, date(2026, 3, 1)),
        ],
    )
    def test_add_months_wraps_years(self, start: date, count: int, expected: date) -> None:
        assert add_months(start, count) == expected

    def test_month_range_is_inclusive_and_crosses_years(self) -> None:
        assert month_range(date(2025, 11, 15), date(2026, 2, 3)) == [
            date(2025, 11, 1),
            date(2025, 12, 1),
            date(2026, 1, 1),
            date(2026, 2, 1),
        ]

    def test_month_range_of_one_month(self) -> None:
        assert month_range(date(2026, 5, 9), date(2026, 5, 20)) == [date(2026, 5, 1)]

    def test_goal_created_month_ignores_the_day(self) -> None:
        created = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
        assert goal_created_month(created, "America/Bogota") == date(2026, 3, 1)

    def test_goal_created_month_uses_the_local_calendar(self) -> None:
        # 23:30 on Oct 31 in Bogota is already Nov 1 in UTC: the local month is October.
        assert goal_created_month(BOGOTA_LATE_NIGHT, "America/Bogota") == date(2026, 10, 1)
        assert goal_created_month(BOGOTA_LATE_NIGHT, "UTC") == date(2026, 11, 1)

    def test_month_key(self) -> None:
        assert month_key(date(2026, 3, 1)) == "2026-03"
