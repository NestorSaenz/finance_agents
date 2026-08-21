"""Unit tests for the unified movement finder (services stubbed)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from app.shared.types import MovementKind, TransactionType
from app.src.analysis.services.movement_finder import MovementFinder
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import CardPaymentView
from app.src.goals.interfaces import GoalServiceABC
from app.src.goals.models import GoalContributionView
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import Transaction

pytestmark = pytest.mark.asyncio

USER = "u1"
TODAY = date(2026, 8, 13)


def _tx(
    description: str,
    amount: str,
    on: date,
    ttype: TransactionType = TransactionType.EXPENSE,
    category: str = "otros",
) -> Transaction:
    return Transaction(
        id=f"tx-{description}",
        user_id=USER,
        amount=Decimal(amount),
        currency="MXN",
        transaction_type=ttype,
        description=description,
        category=category,
        transaction_date=on,
        budget_date=on,
        source="manual",
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


class _StubTransactions:
    def __init__(self, items: list[Transaction]) -> None:
        self._items = items
        self.calls: list[tuple[date, date]] = []

    async def list_by_period(
        self, user_id: str, *, period_start: date, period_end: date, **_: Any
    ) -> list[Transaction]:
        self.calls.append((period_start, period_end))
        return [t for t in self._items if period_start <= t.transaction_date <= period_end]


class _StubCards:
    def __init__(self, payments: list[CardPaymentView]) -> None:
        self._payments = payments

    async def list_payments(
        self, user_id: str, period_start: date, period_end: date
    ) -> list[CardPaymentView]:
        return [
            p for p in self._payments if period_start <= p.payment_date <= period_end
        ]


class _StubGoals:
    def __init__(self, contributions: list[GoalContributionView]) -> None:
        self._contributions = contributions

    async def list_contributions_in_period(
        self, user_id: str, period_start: date, period_end: date
    ) -> list[GoalContributionView]:
        return [
            c
            for c in self._contributions
            if period_start <= c.contribution_date <= period_end
        ]


def _finder(
    txs: list[Transaction] | None = None,
    payments: list[CardPaymentView] | None = None,
    contributions: list[GoalContributionView] | None = None,
) -> MovementFinder:
    return MovementFinder(
        cast(TransactionServiceABC, _StubTransactions(txs or [])),
        cast(CreditCardServiceABC, _StubCards(payments or [])),
        cast(GoalServiceABC, _StubGoals(contributions or [])),
    )


async def test_finds_goal_contribution_by_amount() -> None:
    # The reported bug: an aporte a meta must be findable by amount (it lives in
    # goal_contributions, which delete_transaction never searches).
    finder = _finder(
        contributions=[
            GoalContributionView(
                goal_name="Fondo de Emergencias",
                amount=Decimal("8915400"),
                contribution_date=date(2026, 8, 12),
            )
        ]
    )
    results = await finder.find_movements(
        USER, amount=Decimal("8915400"), today=TODAY
    )
    assert len(results) == 1
    assert results[0].kind == MovementKind.GOAL_CONTRIBUTION
    assert results[0].label == "Fondo de Emergencias"
    assert results[0].amount == Decimal("8915400")


async def test_searches_all_history_when_amount_given() -> None:
    # An amount is a strong key: the window must span all history, not just recent
    # months, so an old movement is still found.
    txs = [_tx("Compra vieja", "500", date(2024, 1, 5))]
    finder = _finder(txs=txs)
    results = await finder.find_movements(USER, amount=Decimal("500"), today=TODAY)
    assert len(results) == 1
    assert results[0].kind == MovementKind.EXPENSE


async def test_retiro_is_positive_magnitude_with_withdrawal_kind() -> None:
    finder = _finder(
        contributions=[
            GoalContributionView(
                goal_name="Viaje",
                amount=Decimal("-2000"),
                contribution_date=date(2026, 8, 10),
            )
        ]
    )
    results = await finder.find_movements(USER, amount=Decimal("2000"), today=TODAY)
    assert len(results) == 1
    assert results[0].kind == MovementKind.GOAL_WITHDRAWAL
    assert results[0].amount == Decimal("2000")  # positive magnitude


async def test_text_filter_matches_across_sources() -> None:
    finder = _finder(
        txs=[_tx("Mercado", "300", date(2026, 8, 5))],
        payments=[
            CardPaymentView(
                card_id="c-nu",
                card_name="Nu",
                amount=Decimal("400"),
                payment_date=date(2026, 8, 6),
            )
        ],
    )
    results = await finder.find_movements(USER, text="nu", today=TODAY)
    assert len(results) == 1
    assert results[0].kind == MovementKind.CARD_PAYMENT


async def test_text_matches_transaction_category() -> None:
    finder = _finder(txs=[_tx("MERCA FACIL", "300", date(2026, 8, 5), category="mercado")])
    results = await finder.find_movements(USER, text="mercado", today=TODAY)
    assert len(results) == 1
    assert results[0].label == "MERCA FACIL"


async def test_text_only_searches_all_history() -> None:
    # A text filter is selective, so it must reach an OLD movement (not just the
    # current + previous month) — "quita ese aporte a emergencia" months later.
    finder = _finder(
        contributions=[
            GoalContributionView(
                goal_name="Fondo de emergencia",
                amount=Decimal("1000"),
                contribution_date=date(2026, 1, 10),
            )
        ]
    )
    results = await finder.find_movements(USER, text="emergencias", today=TODAY)
    assert len(results) == 1
    assert results[0].kind == MovementKind.GOAL_CONTRIBUTION


async def test_amount_ignores_misremembered_date() -> None:
    # With an amount (strong key), a wrong date must NOT hide the movement.
    finder = _finder(txs=[_tx("Arriendo", "1000", date(2026, 8, 2))])
    results = await finder.find_movements(
        USER, amount=Decimal("1000"), on_date=date(2026, 8, 9), today=TODAY
    )
    assert len(results) == 1


async def test_date_only_narrows_to_that_day() -> None:
    finder = _finder(
        txs=[
            _tx("A", "100", date(2026, 8, 2)),
            _tx("B", "200", date(2026, 8, 9)),
        ]
    )
    results = await finder.find_movements(USER, on_date=date(2026, 8, 9), today=TODAY)
    assert len(results) == 1
    assert results[0].label == "B"


async def test_results_sorted_newest_first() -> None:
    finder = _finder(
        txs=[
            _tx("Vieja", "50", date(2026, 7, 1)),
            _tx("Nueva", "50", date(2026, 8, 1)),
        ]
    )
    results = await finder.find_movements(USER, amount=Decimal("50"), today=TODAY)
    assert [r.label for r in results] == ["Nueva", "Vieja"]


async def test_income_kind() -> None:
    finder = _finder(
        txs=[_tx("Sueldo", "5000", date(2026, 8, 1), ttype=TransactionType.INCOME)]
    )
    results = await finder.find_movements(USER, amount=Decimal("5000"), today=TODAY)
    assert results[0].kind == MovementKind.INCOME
