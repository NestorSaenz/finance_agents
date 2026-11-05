"""query_budgets must return the TOTAL line(s), summed in code (never by the LLM)."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import pytest

from app.agents.tools.budget_tools import BudgetToolkit
from app.shared.types import BudgetPeriod, CurrencyType
from app.src.budgets.constants import MAX_PAGE_SIZE
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.budgets.models import Budget, BudgetStatus

pytestmark = pytest.mark.asyncio

# Astrid's 16 active budgets; the real sum is 12.700.353 (the model said 12.486.308).
ASTRID_AMOUNTS = [
    400000, 55000, 1334199, 100000, 1107000, 400000, 550000, 119900,
    450000, 562754, 500000, 1500000, 78500, 700000, 3493000, 1350000,
]  # fmt: skip


def _budget(
    index: int,
    amount: int,
    *,
    category: str | None = "",
    period: BudgetPeriod = BudgetPeriod.MONTHLY,
    currency: CurrencyType = CurrencyType.COP,
) -> Budget:
    return Budget(
        id=f"b{index}",
        user_id="u1",
        name=f"Presupuesto {index}",
        amount=Decimal(amount),
        category=f"cat{index}" if category == "" else category,
        currency=currency,
        period_type=period,
        start_date=date(2026, 11, 1),
        end_date=None,
        alert_threshold=Decimal("80"),
        alert_enabled=True,
        is_active=True,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


class _PagedBudgets:
    """Budget service stub that really pages; spends 10% of each tope unless overridden."""

    def __init__(
        self,
        budgets: list[Budget],
        failing: frozenset[str] = frozenset(),
        spent: dict[str, Decimal] | None = None,
    ) -> None:
        self._budgets = budgets
        self._failing = failing
        self._spent = spent or {}
        self.page_sizes: list[int] = []
        self.running = 0
        self.max_running = 0

    @classmethod
    def of(cls, amounts: list[int], **kwargs: object) -> "_PagedBudgets":
        return cls([_budget(i, a) for i, a in enumerate(amounts, start=1)], **kwargs)  # type: ignore[arg-type]

    async def list_budgets(
        self, user_id: str, *, page: int, page_size: int
    ) -> tuple[list[Budget], int]:
        self.page_sizes.append(page_size)
        start = (page - 1) * page_size
        return self._budgets[start : start + page_size], len(self._budgets)

    async def get_budget_status(
        self, budget_id: str, user_id: str, as_of: date | None = None
    ) -> BudgetStatus:
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        await asyncio.sleep(0)  # let the other reads start: shows the real concurrency
        self.running -= 1
        if budget_id in self._failing:
            raise RuntimeError("status unavailable")
        budget = next(b for b in self._budgets if b.id == budget_id)
        spent = self._spent.get(budget_id, budget.amount * Decimal("0.1"))
        return BudgetStatus(
            budget=budget,
            period_start=date(2026, 11, 1),
            period_end=date(2026, 11, 30),
            spent=spent,
            remaining=budget.amount - spent,
            percentage=10.0,
            alert_triggered=False,
        )


async def _query(service: _PagedBudgets) -> str:
    toolkit = BudgetToolkit(cast(BudgetServiceABC, service))
    return await toolkit.dispatch("query_budgets", {}, "u1")


def _total_lines(result: str) -> list[str]:
    return [line for line in result.splitlines() if line.startswith(("TOTAL", "General"))]


async def test_total_line_sums_topes_spent_and_remaining() -> None:
    result = await _query(_PagedBudgets.of([1000, 2500, 500]))

    assert _total_lines(result) == [
        "TOTAL (por categoría): topes $4000 · gastado $400.0 · restan $3600.0 (3 presupuestos)"
    ]


async def test_astrid_case_sums_to_the_real_total() -> None:
    assert sum(ASTRID_AMOUNTS) == 12_700_353

    result = await _query(_PagedBudgets.of(ASTRID_AMOUNTS))

    [line] = _total_lines(result)
    assert line.startswith("TOTAL (por categoría): topes $12700353")  # clean, single line
    assert "12486308" not in result
    assert "(16 presupuestos)" in line
    assert result.startswith("16 presupuesto(s):")


async def test_overall_budget_is_not_added_to_the_category_total() -> None:
    budgets = [
        _budget(1, 3000, category=None),  # overall: already covers the other two
        _budget(2, 1000, category="alimentacion"),
        _budget(3, 500, category="transporte"),
    ]

    result = await _query(_PagedBudgets(budgets))

    assert _total_lines(result) == [
        "TOTAL (por categoría): topes $1500 · gastado $150.0 · restan $1350.0 (2 presupuestos)",
        "General: tope $3000 · gastado $300.0",
    ]


async def test_each_currency_and_period_gets_its_own_total() -> None:
    budgets = [
        _budget(1, 100000, period=BudgetPeriod.WEEKLY),
        _budget(2, 400000, period=BudgetPeriod.MONTHLY),
        _budget(3, 600000, period=BudgetPeriod.MONTHLY),
    ]

    result = await _query(_PagedBudgets(budgets))

    lines = _total_lines(result)
    assert len(lines) == 2
    assert lines[0].startswith("TOTAL semanal (COP) (por categoría): topes $100000")
    assert lines[1].startswith("TOTAL mensual (COP) (por categoría): topes $1000000")


async def test_overspent_budgets_are_counted_even_when_the_net_is_positive() -> None:
    budgets = [_budget(1, 1000), _budget(2, 5000)]
    service = _PagedBudgets(budgets, spent={"b1": Decimal("1500")})  # b1 over by 500

    [line] = _total_lines(await _query(service))

    assert "restan $4000.0" in line  # net: hides the overspend...
    assert line.endswith("(2 presupuestos) (1 pasado)")  # ...so the line says it


async def test_more_than_one_page_of_budgets_are_all_listed_and_summed() -> None:
    amounts = [1000] * (MAX_PAGE_SIZE + 25)
    service = _PagedBudgets.of(amounts)

    result = await _query(service)

    [line] = _total_lines(result)
    assert len(service.page_sizes) == 2  # paged, not truncated at 20
    assert f"topes ${1000 * len(amounts)}" in line
    assert f"({len(amounts)} presupuestos)" in line
    assert result.count("\n- ") == len(amounts)


async def test_more_than_twenty_budgets_are_not_truncated() -> None:
    [line] = _total_lines(await _query(_PagedBudgets.of([100] * 30)))

    assert "topes $3000" in line and "(30 presupuestos)" in line


async def test_failed_status_keeps_its_place_and_its_tope() -> None:
    service = _PagedBudgets.of([1000, 2000, 3000], failing=frozenset({"b2"}))

    result = await _query(service)

    [line] = _total_lines(result)
    assert "topes $6000 (3 presupuestos)" in line  # the failed one is in the topes
    assert "gastado $400.0" in line  # only the two with data (100 + 300)
    assert "solo de los 2 con datos" in line
    assert "sin datos de gasto: Presupuesto 2" in line
    listed = [x for x in result.splitlines() if x.startswith("- ")]
    assert "Presupuesto 2: límite $2000" in listed[1]  # original order, not moved to the end


async def test_status_reads_run_concurrently_but_bounded() -> None:
    service = _PagedBudgets.of([100] * 30)

    await _query(service)

    assert 1 < service.max_running <= 8


async def test_no_budgets_has_no_total() -> None:
    assert await _query(_PagedBudgets([])) == "No tienes presupuestos configurados."
