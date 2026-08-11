"""Unit tests for the holistic financial analysis service."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.shared.types import CategoryType, CurrencyType, UserId
from app.src.analysis.services.analysis_service import AnalysisService
from app.src.budgets.models import Budget, BudgetStatus
from app.src.cards.models import CreditCard, CreditCardStatus
from app.src.goals.models import Goal
from app.src.transactions.models import CategorySpending, SpendingSummary
from app.src.users.models import UserProfile

pytestmark = pytest.mark.asyncio


class FakeTransactions:
    async def get_spending_summary(self, user_id, *, period_start, period_end):  # type: ignore[no-untyped-def]
        return SpendingSummary(
            total_income=Decimal("30000"),
            total_expenses=Decimal("200000"),
            by_category=[
                CategorySpending(category=CategoryType.ALIMENTACION, amount=Decimal("200000"))
            ],
            cash_expenses=Decimal("5000"),
        )


class FakeBudgets:
    async def get_all_status(self, user_id, as_of=None):  # type: ignore[no-untyped-def]
        budget = Budget(
            id="b1",
            user_id=user_id,
            name="Comida",
            amount=Decimal("600000"),
            category=CategoryType.ALIMENTACION,
            currency=CurrencyType.MXN,
            period_type="monthly",
            start_date=date(2026, 7, 1),
            end_date=None,
            alert_threshold=Decimal("80"),
            alert_enabled=True,
            is_active=True,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
        return [
            BudgetStatus(
                budget=budget,
                period_start=date(2026, 7, 1),
                period_end=date(2026, 7, 31),
                spent=Decimal("200000"),
                remaining=Decimal("400000"),
                percentage=33.0,
                alert_triggered=False,
            )
        ]


class FakeGoals:
    async def contributed_in_period(self, user_id, period_start, period_end):  # type: ignore[no-untyped-def]
        return Decimal("2000")

    async def list_goals(self, user_id, *, page, page_size, as_of=None):  # type: ignore[no-untyped-def]
        goal = Goal(
            id="g1",
            user_id=user_id,
            name="vacaciones playa",
            description=None,
            goal_type="savings",
            target_amount=Decimal("50000"),
            current_amount=Decimal("20000"),
            currency=CurrencyType.MXN,
            target_date=None,
            monthly_contribution=None,
            status="active",
            priority=1,
            created_at=datetime(2026, 7, 1, tzinfo=UTC),
        )
        return [goal], 1


class FakeCards:
    async def total_paid_up_to(self, user_id, as_of):  # type: ignore[no-untyped-def]
        return Decimal("8000")

    async def get_all_status(self, user_id, as_of=None):  # type: ignore[no-untyped-def]
        card = CreditCard(
            id="c1",
            user_id=user_id,
            name="Visa BBVA",
            credit_limit=Decimal("5000000"),
            cutoff_day=15,
            payment_day=5,
            is_active=True,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        return [
            CreditCardStatus(
                card=card,
                cycle_start=date(2026, 6, 16),
                cycle_end=date(2026, 7, 15),
                spent_cycle=Decimal("200000"),
                balance=Decimal("500000"),
                available=Decimal("4500000"),
                utilization=10.0,
                next_payment_date=date(2026, 8, 5),
            )
        ]


class FakeProfiles:
    async def get_profile(self, user_id: UserId) -> UserProfile:
        return UserProfile(
            user_id=user_id,
            monthly_income=Decimal("10000000"),
            savings_goal_percentage=Decimal("20"),
            onboarding_completed=True,
        )


def _service() -> AnalysisService:
    return AnalysisService(
        FakeTransactions(),  # type: ignore[arg-type]
        FakeBudgets(),  # type: ignore[arg-type]
        FakeGoals(),  # type: ignore[arg-type]
        FakeCards(),  # type: ignore[arg-type]
        FakeProfiles(),  # type: ignore[arg-type]
    )


async def test_snapshot_registered_income_replaces_base() -> None:
    # The profile base is a fallback: with income logged this month, it counts as
    # the total (not base + registered), so the base doesn't double-count.
    snap = await _service().snapshot("u1", "este_mes")

    assert snap.income_base == Decimal("10000000")
    assert snap.income_registered == Decimal("30000")
    assert snap.total_income == Decimal("30000")  # registered replaces the base
    assert snap.disposable == Decimal("-170000")  # 30k - 200k


async def test_snapshot_computes_savings_target_from_total_income() -> None:
    snap = await _service().snapshot("u1", "este_mes")

    # 20% of 30,000 (the effective income)
    assert snap.savings_target_amount == Decimal("6000")


class _NoIncomeTransactions(FakeTransactions):
    async def get_spending_summary(self, user_id, *, period_start, period_end):  # type: ignore[no-untyped-def]
        return SpendingSummary(
            total_income=Decimal("0"),
            total_expenses=Decimal("50000"),
            by_category=[],
        )


async def test_snapshot_falls_back_to_base_when_no_registered_income() -> None:
    service = AnalysisService(
        _NoIncomeTransactions(),  # type: ignore[arg-type]
        FakeBudgets(),  # type: ignore[arg-type]
        FakeGoals(),  # type: ignore[arg-type]
        FakeCards(),  # type: ignore[arg-type]
        FakeProfiles(),  # type: ignore[arg-type]
    )

    snap = await service.snapshot("u1", "este_mes")

    assert snap.income_registered == Decimal("0")
    assert snap.total_income == Decimal("10000000")  # base used as fallback


async def test_snapshot_aggregates_cards_and_goals() -> None:
    snap = await _service().snapshot("u1", "este_mes")

    assert snap.card_debt_total == Decimal("500000")
    assert snap.card_available_total == Decimal("4500000")
    assert snap.goals[0].percentage == pytest.approx(40.0)
    assert snap.by_category[0].percentage == pytest.approx(100.0)


async def test_snapshot_excludes_reference_income_for_other_periods() -> None:
    snap = await _service().snapshot("u1", "todo")

    # The monthly reference income doesn't apply to "todo".
    assert snap.income_base == Decimal("0")
    assert snap.total_income == Decimal("30000")


async def test_accumulated_surplus_subtracts_cash_cards_and_goals() -> None:
    # Free cash = income − cash spent − card payments − goal contributions.
    # 30,000 − 5,000 − 8,000 − 2,000 = 15,000.
    surplus = await _service().accumulated_surplus("u1", date(2026, 8, 31))

    assert surplus == Decimal("15000")
