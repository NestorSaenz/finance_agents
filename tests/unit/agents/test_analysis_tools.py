"""Unit tests for the holistic analysis toolkit."""

from datetime import date
from decimal import Decimal

import pytest

from app.agents.tools.analysis_tools import ANALYZE_FINANCES_TOOL, AnalysisToolkit
from app.shared.types import CategoryType, UserId
from app.src.analysis.models import (
    CardLine,
    CategoryLine,
    FinancialSnapshot,
    GoalLine,
)

pytestmark = pytest.mark.asyncio


def _snapshot() -> FinancialSnapshot:
    return FinancialSnapshot(
        period="este_mes",
        income_base=Decimal("10000000"),
        income_registered=Decimal("30000"),
        total_income=Decimal("10030000"),
        total_expenses=Decimal("200000"),
        disposable=Decimal("9830000"),
        savings_target_pct=Decimal("20"),
        savings_target_amount=Decimal("2006000"),
        by_category=[
            CategoryLine(
                category=CategoryType.ALIMENTACION, amount=Decimal("200000"), percentage=100.0
            )
        ],
        budgets=[],
        goals=[
            GoalLine(
                name="vacaciones playa",
                current=Decimal("20000"),
                target=Decimal("50000"),
                percentage=40.0,
            )
        ],
        cards=[
            CardLine(
                name="Visa BBVA",
                balance=Decimal("500000"),
                limit=Decimal("5000000"),
                available=Decimal("4500000"),
                next_payment_date=date(2026, 8, 5),
            )
        ],
        card_debt_total=Decimal("500000"),
        card_available_total=Decimal("4500000"),
    )


class FakeAnalysis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def snapshot(self, user_id: UserId, period: str) -> FinancialSnapshot:
        self.calls.append((user_id, period))
        return _snapshot()


async def test_analyze_finances_formats_grounded_facts() -> None:
    service = FakeAnalysis()
    result = await AnalysisToolkit(service).dispatch(  # type: ignore[arg-type]
        ANALYZE_FINANCES_TOOL, {"period": "este_mes"}, "u1"
    )

    assert service.calls[0] == ("u1", "este_mes")
    # Key grounded numbers present (formatted with thousands separators).
    assert "10,030,000" in result  # total income
    assert "9,830,000" in result  # disposable
    assert "2,006,000" in result  # savings target
    assert "Visa BBVA" in result
    assert "vacaciones playa" in result
    assert "Alimentación" in result  # category label


async def test_defaults_to_este_mes() -> None:
    service = FakeAnalysis()
    await AnalysisToolkit(service).dispatch(ANALYZE_FINANCES_TOOL, {}, "u1")  # type: ignore[arg-type]
    assert service.calls[0] == ("u1", "este_mes")
