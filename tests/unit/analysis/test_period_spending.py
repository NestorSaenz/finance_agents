"""Goal savings as spending: period_spending, snapshot and monthly_trend (Astrid's cases).

Money already set aside into goals (real contributions) counts as spending of its month
from ``GOALS_COUNT_AS_SPENDING_FROM`` on; a plan not yet contributed never counts; the
consumption summary (``total_expenses``) and the accumulated surplus are untouched.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.core.config import settings
from app.src.analysis.services.analysis_service import AnalysisService
from app.src.goals.models import GoalFlows, GoalMonthContribution
from app.src.transactions.models import SpendingSummary
from tests.fakes import InMemoryContributionLedger

pytestmark = pytest.mark.asyncio

D = Decimal
CUTOFF = date(2026, 11, 1)
INCOME, CONSUMPTION, CASH, CREDIT = D("3000000"), D("1000000"), D("600000"), D("400000")
CARD_PAID = D("100000")


class FakeTransactions:
    """Same summary for any window (the consumption does not depend on goals)."""

    def __init__(self) -> None:
        self.windows: list[tuple[date, date]] = []

    async def get_spending_summary(self, user_id, *, period_start, period_end):  # type: ignore[no-untyped-def]
        self.windows.append((period_start, period_end))
        return SpendingSummary(
            total_income=INCOME,
            total_expenses=CONSUMPTION,
            by_category=[],
            credit_expenses=CREDIT,
            cash_expenses=CASH,
        )


class FakeGoals:
    """Goal flows computed from a real ledger, counting the provider calls."""

    def __init__(self, ledger: InMemoryContributionLedger) -> None:
        self.ledger = ledger
        self.monthly_calls = 0
        self.flow_calls: list[tuple[date, date]] = []

    async def flows_in_period(self, user_id, start, end):  # type: ignore[no-untyped-def]
        self.flow_calls.append((start, end))
        rows = await self.ledger.list_in_period(user_id, start, end)
        return GoalFlows(
            saved=sum((c.amount for c in rows if c.amount > 0), start=D("0")),
            withdrawn=sum((-c.amount for c in rows if c.amount < 0), start=D("0")),
        )

    async def monthly_flows(self, user_id, start, end):  # type: ignore[no-untyped-def]
        self.monthly_calls += 1
        rows = await self.ledger.list_in_period(user_id, start, end)
        months = sorted({(c.goal_id, c.contribution_date.replace(day=1)) for c in rows})
        return [
            GoalMonthContribution(
                goal_id=goal_id,
                month=month,
                saved=sum(
                    (c.amount for c in rows if c.goal_id == goal_id and c.contribution_date.replace(day=1) == month and c.amount > 0),
                    start=D("0"),
                ),
                withdrawn=D("0"),
            )
            for goal_id, month in months
        ]

    async def contributed_in_period(self, user_id, start, end):  # type: ignore[no-untyped-def]
        return await self.ledger.sum_in_period(user_id, start, end)

    async def list_goals(self, user_id, *, page, page_size, as_of=None):  # type: ignore[no-untyped-def]
        return [], 0

    async def get_monthly_history(self, user_id, months=6, to_month=None, today=None):  # type: ignore[no-untyped-def]
        return []


class FakeCards:
    async def total_paid_up_to(self, user_id, as_of):  # type: ignore[no-untyped-def]
        return CARD_PAID

    async def get_all_status(self, user_id, as_of=None):  # type: ignore[no-untyped-def]
        return []


class FakeBudgets:
    async def get_all_status(self, user_id, as_of=None):  # type: ignore[no-untyped-def]
        return []


class FakeProfiles:
    async def get_profile(self, user_id):  # type: ignore[no-untyped-def]
        from app.src.users.models import UserProfile

        return UserProfile(user_id=user_id, onboarding_completed=True)


def _service(
    ledger: InMemoryContributionLedger,
) -> tuple[AnalysisService, FakeGoals, FakeTransactions]:
    transactions, goals = FakeTransactions(), FakeGoals(ledger)
    service = AnalysisService(
        transactions,  # type: ignore[arg-type]
        FakeBudgets(),  # type: ignore[arg-type]
        goals,  # type: ignore[arg-type]
        FakeCards(),  # type: ignore[arg-type]
        FakeProfiles(),  # type: ignore[arg-type]
    )
    return service, goals, transactions


@pytest.fixture(autouse=True)
def cutoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "GOALS_COUNT_AS_SPENDING_FROM", CUTOFF)


NOVEMBER = (date(2026, 11, 1), date(2026, 11, 30))


class TestPeriodSpending:
    async def test_a_plan_without_a_contribution_does_not_count(self) -> None:
        # A plan lives in goal_plans, never in the ledger: nothing was moved.
        service, _, _ = _service(InMemoryContributionLedger())

        spending = await service.period_spending("u1", *NOVEMBER)

        assert spending.total_spent == CONSUMPTION
        assert spending.balance == INCOME - CONSUMPTION  # same as before goals counted
        assert spending.goal_saved == D("0")

    async def test_a_real_contribution_counts_as_spending(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("500000"), date(2026, 11, 5))
        service, _, _ = _service(ledger)

        spending = await service.period_spending("u1", *NOVEMBER)

        assert spending.goal_saved == D("500000")
        assert spending.total_spent == CONSUMPTION + D("500000")
        assert spending.balance == INCOME - CONSUMPTION - D("500000")
        # The consumption summary itself is untouched.
        assert spending.summary.total_expenses == CONSUMPTION
        assert spending.summary.credit_expenses + spending.summary.cash_expenses == CONSUMPTION

    async def test_a_contribution_before_the_cutoff_does_not_count(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("700000"), date(2026, 10, 20))  # backfilled history
        service, _, _ = _service(ledger)

        spending = await service.period_spending("u1", date(2026, 10, 1), date(2026, 10, 31))

        assert spending.goal_saved == D("0")
        assert spending.total_spent == CONSUMPTION

    async def test_a_period_crossing_the_cutoff_counts_only_the_part_from_it(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("300000"), date(2026, 10, 20))
        ledger.add("g1", D("200000"), date(2026, 11, 5))
        ledger.add("g1", D("-50000"), date(2026, 10, 25))
        ledger.add("g1", D("-30000"), date(2026, 11, 9))
        service, _, _ = _service(ledger)

        spending = await service.period_spending("u1", date(2026, 10, 1), date(2026, 11, 30))

        assert spending.goal_saved == D("200000")  # only the tail >= the cutoff
        # The withdrawals use the SAME cutoff: no asymmetry with what was set aside.
        assert spending.goal_withdrawn == D("30000")

    async def test_a_month_with_only_withdrawals_spends_only_the_consumption(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("-80000"), date(2026, 11, 7))
        service, _, _ = _service(ledger)

        spending = await service.period_spending("u1", *NOVEMBER)

        assert spending.total_spent == CONSUMPTION  # the money coming back never lowers it
        assert spending.goal_withdrawn == D("80000")
        assert spending.goal_saved == D("0")

    async def test_withdrawals_before_the_cutoff_are_not_reported(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("7800000"), date(2026, 7, 10))
        ledger.add("g1", D("-720000"), date(2026, 7, 20))
        service, _, _ = _service(ledger)

        july = await service.period_spending("u1", date(2026, 7, 1), date(2026, 7, 31))

        assert (july.goal_saved, july.goal_withdrawn) == (D("0"), D("0"))

    async def test_a_period_covering_everything_reports_only_withdrawals_from_the_cutoff(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("-720000"), date(2026, 7, 20))
        ledger.add("g1", D("-40000"), date(2026, 11, 3))
        service, _, _ = _service(ledger)

        everything = await service.period_spending("u1", date(1970, 1, 1), date(2026, 11, 30))

        assert everything.goal_withdrawn == D("40000")

    async def test_the_surplus_still_uses_the_unclipped_flows(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("-720000"), date(2026, 7, 20))  # before the cutoff
        service, _, _ = _service(ledger)

        surplus = await service.accumulated_surplus("u1", date(2026, 11, 30))

        assert surplus == INCOME - CASH - CARD_PAID + D("720000")

    async def test_contribution_limits_are_inclusive(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("10"), date(2026, 11, 1))
        ledger.add("g1", D("20"), date(2026, 11, 30))
        ledger.add("g1", D("40"), date(2026, 12, 1))
        service, _, _ = _service(ledger)

        assert (await service.period_spending("u1", *NOVEMBER)).goal_saved == D("30")


class TestSnapshot:
    async def test_disposable_includes_the_goal_savings_and_consumption_stays_apart(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("500000"), date(2026, 11, 5))
        ledger.add("g1", D("-120000"), date(2026, 11, 8))
        service, _, _ = _service(ledger)

        snap = await service.snapshot("u1", "2026-11")

        assert snap.total_expenses == CONSUMPTION  # consumption only
        assert snap.goal_saved == D("500000")
        assert snap.goal_withdrawn == D("120000")
        assert snap.disposable == INCOME - CONSUMPTION - D("500000")

    async def test_the_snapshot_and_the_summary_endpoint_report_the_same_figures(self) -> None:
        from app.src.analysis.dto import PeriodSpendingResponse

        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("500000"), date(2026, 11, 5))
        ledger.add("g1", D("-120000"), date(2026, 11, 8))
        ledger.add("g1", D("-720000"), date(2026, 10, 8))  # before the cutoff
        service, _, _ = _service(ledger)

        snap = await service.snapshot("u1", "2026-11")
        body = PeriodSpendingResponse.from_domain(
            await service.period_spending("u1", *NOVEMBER), "2026-11", CUTOFF
        )

        assert (snap.goal_saved, snap.goal_withdrawn) == (body.goal_saved, body.goal_withdrawn)
        assert body.goal_withdrawn == D("120000")


class TestAccumulatedSurplusIsUnchanged:
    async def test_same_value_as_the_standing_formula(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("500000"), date(2026, 11, 5))
        ledger.add("g1", D("-100000"), date(2026, 11, 9))
        service, _, _ = _service(ledger)

        surplus = await service.accumulated_surplus("u1", date(2026, 11, 30))

        # income - cash - card payments - NET goal contributions (not total_spent).
        net = D("500000") - D("100000")
        assert surplus == INCOME - CASH - CARD_PAID - net
        spending = await service.period_spending("u1", *NOVEMBER)
        assert surplus != INCOME - spending.total_spent  # a different, unchanged formula


class TestMonthlyTrend:
    async def test_one_provider_call_and_goal_savings_per_month_respecting_the_cutoff(self) -> None:
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("900000"), date(2026, 9, 12))  # before the cutoff: ignored
        ledger.add("g1", D("700000"), date(2026, 10, 12))  # before the cutoff: ignored
        ledger.add("g1", D("500000"), date(2026, 11, 5))
        ledger.add("g2", D("100000"), date(2026, 11, 6))
        service, goals, _ = _service(ledger)

        trend = await service.monthly_trend("u1", 3, today=date(2026, 11, 10))

        assert goals.monthly_calls == 1  # a single read for the whole window
        assert goals.flow_calls == []  # no per-month queries (the cutoff is a month start)
        assert [m.month for m in trend] == ["2026-09", "2026-10", "2026-11"]
        assert [m.goal_saved for m in trend] == [D("0"), D("0"), D("600000")]
        assert [m.expenses for m in trend] == [CONSUMPTION, CONSUMPTION, CONSUMPTION + D("600000")]
        assert trend[-1].balance == INCOME - CONSUMPTION - D("600000")

    async def test_a_cutoff_inside_a_month_counts_only_its_tail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "GOALS_COUNT_AS_SPENDING_FROM", date(2026, 11, 15))
        ledger = InMemoryContributionLedger()
        ledger.add("g1", D("100"), date(2026, 11, 10))  # before the cutoff day
        ledger.add("g1", D("40"), date(2026, 11, 20))
        service, _, _ = _service(ledger)

        trend = await service.monthly_trend("u1", 2, today=date(2026, 11, 30))

        assert trend[-1].goal_saved == D("40")


def test_the_cutoff_defaults_to_november_first_2026() -> None:
    from app.core.config import Settings

    assert Settings.model_fields["GOALS_COUNT_AS_SPENDING_FROM"].default == date(2026, 11, 1)
