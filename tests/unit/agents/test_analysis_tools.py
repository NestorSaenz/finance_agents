"""Unit tests for the holistic analysis toolkit."""

from datetime import date
from decimal import Decimal

import pytest

from app.agents.tools.analysis_tools import (
    ANALYZE_FINANCES_TOOL,
    SPENDING_TREND_TOOL,
    AnalysisToolkit,
)
from app.shared.types import CategoryType, UserId
from app.src.analysis.constants import (
    DEFAULT_TREND_MONTHS,
    MAX_TREND_MONTHS,
    MIN_TREND_MONTHS,
)
from app.src.analysis.models import (
    CardLine,
    CategoryLine,
    FinancialSnapshot,
    GoalLine,
    MonthlyTotals,
)

pytestmark = pytest.mark.asyncio


def _snapshot() -> FinancialSnapshot:
    return FinancialSnapshot(
        period="este_mes",
        income_base=Decimal("10000000"),
        income_registered=Decimal("30000"),
        # Base is a fallback: with income logged, total == registered (not summed).
        total_income=Decimal("30000"),
        total_expenses=Decimal("200000"),
        # 120k credit + 80k cash: credit + cash always equals total_expenses (an
        # untagged expense is classified by whether it's linked to a card).
        credit_expenses=Decimal("120000"),
        cash_expenses=Decimal("80000"),
        disposable=Decimal("-170000"),
        savings_target_pct=Decimal("20"),
        savings_target_amount=Decimal("6000"),
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
    def __init__(self, trend: list[MonthlyTotals] | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.todays: list[date | None] = []
        self.trend_calls: list[tuple[str, int, date | None]] = []
        self._trend = trend if trend is not None else []

    async def snapshot(
        self, user_id: UserId, period: str, today: date | None = None
    ) -> FinancialSnapshot:
        self.calls.append((user_id, period))
        self.todays.append(today)
        return _snapshot()

    async def monthly_trend(
        self, user_id: UserId, months: int, today: date | None = None
    ) -> list[MonthlyTotals]:
        self.trend_calls.append((user_id, months, today))
        return self._trend


def _month(key: str, income: str, expenses: str) -> MonthlyTotals:
    return MonthlyTotals(
        month=key,
        income=Decimal(income),
        expenses=Decimal(expenses),
        balance=Decimal(income) - Decimal(expenses),
    )


async def test_analyze_finances_formats_grounded_facts() -> None:
    service = FakeAnalysis()
    result = await AnalysisToolkit(service).dispatch(  # type: ignore[arg-type]
        ANALYZE_FINANCES_TOOL, {"period": "este_mes"}, "u1"
    )

    assert service.calls[0] == ("u1", "este_mes")
    # Key grounded numbers present (formatted with thousands separators).
    assert "30,000" in result  # effective income (registered replaces base)
    assert "registrados este mes" in result  # no "base + registrados = " line
    assert "170,000" in result  # disposable
    assert "6,000" in result  # savings target
    assert "Visa BBVA" in result
    assert "vacaciones playa" in result
    assert "Alimentación" in result  # category label


async def test_snapshot_surfaces_cash_vs_credit_split() -> None:
    result = await AnalysisToolkit(FakeAnalysis()).dispatch(  # type: ignore[arg-type]
        ANALYZE_FINANCES_TOOL, {}, "u1"
    )

    assert "GASTOS POR MÉTODO DE PAGO" in result
    assert "crédito $120,000 (60%)" in result
    assert "efectivo/débito $80,000 (40%)" in result
    # credit + cash always covers the full total_expenses now — no third bucket.
    assert "sin método registrado" not in result


async def test_payment_split_omitted_when_there_are_no_expenses() -> None:
    class NoExpenses(FakeAnalysis):
        async def snapshot(
            self, user_id: UserId, period: str, today: date | None = None
        ) -> FinancialSnapshot:
            return _snapshot().model_copy(
                update={
                    "total_expenses": Decimal("0"),
                    "credit_expenses": Decimal("0"),
                    "cash_expenses": Decimal("0"),
                }
            )

    result = await AnalysisToolkit(NoExpenses()).dispatch(  # type: ignore[arg-type]
        ANALYZE_FINANCES_TOOL, {}, "u1"
    )
    assert "MÉTODO DE PAGO" not in result


async def test_spending_trend_formats_months_and_change() -> None:
    service = FakeAnalysis(
        [
            _month("2026-05", "1000000", "400000"),
            _month("2026-06", "1000000", "500000"),
            _month("2026-07", "1000000", "250000"),
        ]
    )
    result = await AnalysisToolkit(service).dispatch(  # type: ignore[arg-type]
        SPENDING_TREND_TOOL, {"months_back": 3}, "u1"
    )

    assert service.trend_calls[0][:2] == ("u1", 3)
    assert "mayo de 2026" in result and "junio de 2026" in result
    assert "+25% vs mes anterior" in result  # 400k -> 500k
    assert "-50% vs mes anterior" in result  # 500k -> 250k
    assert "Mayor gasto: junio de 2026" in result
    assert "Menor gasto: julio de 2026" in result
    assert "PROMEDIO" in result


async def test_spending_trend_defaults_and_clamps_months_back() -> None:
    for argument, expected in (
        ({}, DEFAULT_TREND_MONTHS),
        ({"months_back": "no"}, DEFAULT_TREND_MONTHS),
        ({"months_back": 99}, MAX_TREND_MONTHS),
        ({"months_back": 1}, MIN_TREND_MONTHS),
    ):
        service = FakeAnalysis([_month("2026-07", "0", "1000")])
        await AnalysisToolkit(service).dispatch(SPENDING_TREND_TOOL, argument, "u1")  # type: ignore[arg-type]
        assert service.trend_calls[0][1] == expected


async def test_spending_trend_reports_months_without_movements() -> None:
    service = FakeAnalysis(
        [_month("2026-06", "0", "0"), _month("2026-07", "1000000", "300000")]
    )
    result = await AnalysisToolkit(service).dispatch(  # type: ignore[arg-type]
        SPENDING_TREND_TOOL, {"months_back": 2}, "u1"
    )

    assert "junio de 2026: sin movimientos" in result
    # The empty month is excluded from the average and from the min/max picks.
    assert "1 mes(es) con movimientos" in result
    assert "Menor gasto: julio de 2026" in result


async def test_spending_trend_with_no_data_says_so() -> None:
    service = FakeAnalysis([_month("2026-06", "0", "0"), _month("2026-07", "0", "0")])
    result = await AnalysisToolkit(service).dispatch(  # type: ignore[arg-type]
        SPENDING_TREND_TOOL, {"months_back": 2}, "u1"
    )
    assert result == "No hay movimientos registrados en los últimos 2 meses."


async def test_spending_trend_threads_bound_local_today() -> None:
    from app.shared.clock import bound_today

    service = FakeAnalysis([_month("2026-08", "0", "1000")])
    with bound_today(date(2026, 8, 11)):
        await AnalysisToolkit(service).dispatch(SPENDING_TREND_TOOL, {}, "u1")  # type: ignore[arg-type]
    assert service.trend_calls[0][2] == date(2026, 8, 11)


async def test_unknown_analysis_tool_raises() -> None:
    with pytest.raises(ValueError, match="Unknown analysis tool"):
        await AnalysisToolkit(FakeAnalysis()).dispatch("nope", {}, "u1")  # type: ignore[arg-type]


async def test_defaults_to_este_mes() -> None:
    service = FakeAnalysis()
    await AnalysisToolkit(service).dispatch(ANALYZE_FINANCES_TOOL, {}, "u1")  # type: ignore[arg-type]
    assert service.calls[0] == ("u1", "este_mes")


async def test_threads_bound_local_today_to_snapshot() -> None:
    from app.shared.clock import bound_today

    service = FakeAnalysis()
    with bound_today(date(2026, 8, 11)):
        await AnalysisToolkit(service).dispatch(ANALYZE_FINANCES_TOOL, {}, "u1")  # type: ignore[arg-type]
    # The tool anchors the snapshot's period to the turn's local day.
    assert service.todays == [date(2026, 8, 11)]
