"""Unit tests for budget period computation."""

from datetime import date

from app.shared.types import BudgetPeriod
from app.src.budgets.period import compute_period


class TestComputePeriod:
    def test_monthly_spans_full_month(self) -> None:
        start, end = compute_period(BudgetPeriod.MONTHLY, date(2024, 2, 15))
        assert start == date(2024, 2, 1)
        assert end == date(2024, 2, 29)  # 2024 is a leap year

    def test_yearly_spans_full_year(self) -> None:
        start, end = compute_period(BudgetPeriod.YEARLY, date(2024, 6, 10))
        assert start == date(2024, 1, 1)
        assert end == date(2024, 12, 31)

    def test_weekly_spans_monday_to_sunday(self) -> None:
        # 2024-12-18 is a Wednesday.
        start, end = compute_period(BudgetPeriod.WEEKLY, date(2024, 12, 18))
        assert start == date(2024, 12, 16)  # Monday
        assert end == date(2024, 12, 22)  # Sunday
