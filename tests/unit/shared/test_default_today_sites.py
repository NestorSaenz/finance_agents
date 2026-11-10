"""Every request-time "today" default is the Colombian day, not the UTC one.

All tests are pinned at 2026-10-31T23:30-05:00 (Bogotá) == 2026-11-01T04:30Z, the
moment where a UTC "today" is already the next day (and the next MONTH).
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

from app.shared.clock import bound_today
from app.shared.parsing import parse_date
from app.shared.periods import recent_months, resolve_period
from app.shared.types import TransactionType
from app.src.analysis.services.movement_finder import MovementFinder
from app.src.budgets.models import BudgetSpending
from app.src.budgets.services.budget_service import BudgetService
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.services.credit_card_service import CreditCardService
from app.src.goals.interfaces import GoalServiceABC
from app.src.recurring.models import RecurringCreate
from app.src.transactions.interfaces import TransactionServiceABC
from tests.conftest import BOGOTA_LATE_NIGHT
from tests.unit.budgets.test_budget_service import FakeBudgetRepository, _budget
from tests.unit.cards.test_credit_card_service import (
    FakeCardRepo,
    FakePaymentRepo,
    FakeSpending,
    _card,
)

OCT_31 = date(2026, 10, 31)
NOV_1 = date(2026, 11, 1)

Freeze = Callable[[datetime], None]


def test_the_pinned_moment_is_next_day_in_utc() -> None:
    assert BOGOTA_LATE_NIGHT.astimezone(UTC).date() == NOV_1


def test_este_mes_is_october_in_bogota(freeze_now: Freeze) -> None:
    freeze_now(BOGOTA_LATE_NIGHT)

    assert resolve_period("este_mes") == (date(2026, 10, 1), OCT_31)


def test_recent_months_ends_in_the_bogota_month(freeze_now: Freeze) -> None:
    freeze_now(BOGOTA_LATE_NIGHT)

    assert recent_months(2) == ["2026-09", "2026-10"]


def test_explicit_today_still_wins_over_the_default(freeze_now: Freeze) -> None:
    freeze_now(BOGOTA_LATE_NIGHT)

    assert resolve_period("este_mes", today=date(2026, 12, 5))[0] == date(2026, 12, 1)


def test_bound_today_wins_over_the_default_in_periods(freeze_now: Freeze) -> None:
    freeze_now(BOGOTA_LATE_NIGHT)

    with bound_today(date(2026, 12, 5)):
        assert resolve_period("este_mes")[0] == date(2026, 12, 1)


def test_parse_date_fallback_is_the_bogota_day(freeze_now: Freeze) -> None:
    freeze_now(BOGOTA_LATE_NIGHT)

    assert parse_date(None) == OCT_31
    assert parse_date("not-a-date") == OCT_31


def test_recurring_default_next_run_date_is_evaluated_per_call(freeze_now: Freeze) -> None:
    def make() -> RecurringCreate:
        return RecurringCreate(
            amount=Decimal("1000"),
            description="Arriendo",
            transaction_type=TransactionType.EXPENSE,
            day_of_month=5,
        )

    freeze_now(BOGOTA_LATE_NIGHT)
    first = make().next_run_date
    freeze_now(datetime.fromisoformat("2026-11-02T10:00:00-05:00"))
    second = make().next_run_date

    assert (first, second) == (OCT_31, date(2026, 11, 2))  # not frozen at import time


async def test_card_status_default_uses_the_bogota_day(freeze_now: Freeze) -> None:
    freeze_now(BOGOTA_LATE_NIGHT)
    card = _card(cutoff_day=31)  # the cycle closes on Oct 31 itself: Oct 31 != Nov 1
    service = CreditCardService(
        FakeCardRepo([card]),
        FakePaymentRepo(),
        FakeSpending(cycle=Decimal("0"), total=Decimal("0")),
    )

    default = await service.get_status(card.id, "u1")
    explicit_oct_31 = await service.get_status(card.id, "u1", as_of=OCT_31)
    explicit_nov_1 = await service.get_status(card.id, "u1", as_of=NOV_1)

    assert explicit_oct_31 != explicit_nov_1  # the two days really differ for this card
    assert default == explicit_oct_31


async def test_budget_status_default_period_is_the_bogota_month(freeze_now: Freeze) -> None:
    freeze_now(BOGOTA_LATE_NIGHT)
    periods: list[tuple[date, date]] = []

    class SpyingSpending:
        async def get_spending(
            self, user_id: str, category: Any, period_start: date, period_end: date
        ) -> BudgetSpending:
            periods.append((period_start, period_end))
            return BudgetSpending(total=Decimal("0"), fixed=Decimal("0"))

    service = BudgetService(
        FakeBudgetRepository(budget=_budget()), cast(Any, SpyingSpending())
    )

    await service.get_budget_status("bud-1", "u1")

    assert periods == [(date(2026, 10, 1), OCT_31)]  # not November


async def test_movement_finder_default_window_uses_the_bogota_month(freeze_now: Freeze) -> None:
    freeze_now(BOGOTA_LATE_NIGHT)
    windows: list[tuple[date, date]] = []

    class Txs:
        async def list_by_period(
            self, user_id: str, *, period_start: date, period_end: date, **_: Any
        ) -> list[Any]:
            windows.append((period_start, period_end))
            return []

    class Cards:
        async def list_payments(self, user_id: str, start: date, end: date) -> list[Any]:
            return []

    class Goals:
        async def list_contributions_in_period(
            self, user_id: str, start: date, end: date
        ) -> list[Any]:
            return []

    finder = MovementFinder(
        cast(TransactionServiceABC, Txs()),
        cast(CreditCardServiceABC, Cards()),
        cast(GoalServiceABC, Goals()),
    )

    await finder.find_movements("u1")

    # Previous month start .. end of the CURRENT (October) month.
    assert windows == [(date(2026, 9, 1), OCT_31)]
