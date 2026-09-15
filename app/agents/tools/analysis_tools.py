"""Holistic financial-analysis tool for the assistant.

Exposes a single tool that returns a grounded snapshot of the user's finances
(income, expenses, disposable, budgets, goals, cards) so the LLM can diagnose
the situation and give advice based on real numbers — not guesses.
"""

from decimal import Decimal
from typing import Any

from app.agents.nodes.analyst_constants import get_category_label
from app.core.logging import get_logger
from app.shared.clock import current_today
from app.shared.periods import period_label
from app.shared.types import UserId
from app.src.analysis.constants import (
    DEFAULT_TREND_MONTHS,
    MAX_TREND_MONTHS,
    MIN_TREND_MONTHS,
)
from app.src.analysis.interfaces import AnalysisServiceABC
from app.src.analysis.models import FinancialSnapshot, MonthlyTotals

logger = get_logger(__name__)

ANALYZE_FINANCES_TOOL = "analyze_finances"
SPENDING_TREND_TOOL = "spending_trend"

ANALYSIS_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": ANALYZE_FINANCES_TOOL,
            "description": (
                "Devuelve un panorama COMPLETO de la situación financiera del usuario "
                "(ingresos, gastos, disponible, meta de ahorro, presupuestos, metas y "
                "tarjetas). Úsala para '¿cómo va mi situación financiera?', diagnósticos, "
                "consejos para cumplir metas, o antes de aconsejar sobre una compra o "
                "crédito grande. Con estos datos reales razona y da recomendaciones."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["este_mes", "mes_pasado", "todo"],
                        "description": "Periodo a analizar (por defecto este_mes)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": SPENDING_TREND_TOOL,
            "description": (
                "Compara los ingresos y gastos MES A MES de los últimos meses. "
                "Úsala para '¿cómo ha cambiado mi gasto?', '¿gasto más que el mes "
                "pasado?', '¿en qué mes gasté más?' o cualquier pregunta de "
                "evolución/tendencia. Para UN solo periodo usa analyze_finances."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "months_back": {
                        "type": "integer",
                        "minimum": MIN_TREND_MONTHS,
                        "maximum": MAX_TREND_MONTHS,
                        "description": (
                            f"Cuántos meses comparar, contando el actual "
                            f"(entre {MIN_TREND_MONTHS} y {MAX_TREND_MONTHS}; "
                            f"por defecto {DEFAULT_TREND_MONTHS})"
                        ),
                    },
                },
            },
        },
    },
]


class AnalysisToolkit:
    """Exposes the holistic analysis tool to the LLM."""

    def __init__(self, service: AnalysisServiceABC) -> None:
        self._service = service

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return ANALYSIS_TOOL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        if name == ANALYZE_FINANCES_TOOL:
            period = str(arguments.get("period", "este_mes")).lower()
            snapshot = await self._service.snapshot(
                user_id, period, today=current_today()
            )
            return _format_snapshot(snapshot)
        if name == SPENDING_TREND_TOOL:
            months = _to_months(arguments.get("months_back"))
            trend = await self._service.monthly_trend(
                user_id, months, today=current_today()
            )
            return _format_trend(trend)
        raise ValueError(f"Unknown analysis tool: {name}")


def _money(value: Decimal) -> str:
    """Format an amount with thousands separators and no decimals (pesos)."""
    return f"${value:,.0f}"


def _to_months(value: Any) -> int:
    """Parse ``months_back`` into a bounded month count.

    The model only picks a number: it is clamped to the trend bounds here (and
    again in the service), so an out-of-range or garbage value degrades to a
    sane window instead of failing the turn.
    """
    try:
        months = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TREND_MONTHS
    return max(MIN_TREND_MONTHS, min(months, MAX_TREND_MONTHS))


def _change_note(current: Decimal, previous: Decimal) -> str:
    """'(+12% vs mes anterior)' for a month's expenses, when comparable."""
    if previous <= 0:
        return ""
    change = float((current - previous) / previous * 100)
    return f" ({change:+.0f}% vs mes anterior)"


def _format_trend(months: list[MonthlyTotals]) -> str:
    """Render the month-by-month totals as facts for the LLM to narrate."""
    active = [m for m in months if m.income > 0 or m.expenses > 0]
    if not active:
        return f"No hay movimientos registrados en los últimos {len(months)} meses."

    lines = [
        f"Tendencia mes a mes (últimos {len(months)} meses, por fecha del movimiento):"
    ]
    previous: MonthlyTotals | None = None
    for month in months:
        label = period_label(month.month)
        if month.income == 0 and month.expenses == 0:
            lines.append(f"- {label}: sin movimientos")
        else:
            lines.append(
                f"- {label}: gastos {_money(month.expenses)}"
                f"{_change_note(month.expenses, previous.expenses) if previous else ''}"
                f", ingresos {_money(month.income)}, balance {_money(month.balance)}"
            )
        previous = month

    highest = max(active, key=lambda m: m.expenses)
    lowest = min(active, key=lambda m: m.expenses)
    average = sum((m.expenses for m in active), Decimal("0")) / len(active)
    lines.append(
        f"PROMEDIO de gastos ({len(active)} mes(es) con movimientos): {_money(average)}. "
        f"Mayor gasto: {period_label(highest.month)} ({_money(highest.expenses)}). "
        f"Menor gasto: {period_label(lowest.month)} ({_money(lowest.expenses)})."
    )
    return "\n".join(lines)


def _payment_split_lines(s: FinancialSnapshot) -> list[str]:
    """How the period's expenses split between credit card and cash.

    credit_expenses + cash_expenses always equals total_expenses: an untagged
    expense is classified by whether it's linked to a card (see
    TransactionService.get_spending_summary), so there's no unaccounted remainder.
    """
    if s.total_expenses <= 0:
        return []
    def share(amount: Decimal) -> float:
        return float(amount / s.total_expenses * 100)

    parts = [
        f"crédito {_money(s.credit_expenses)} ({share(s.credit_expenses):.0f}%)",
        f"efectivo/débito {_money(s.cash_expenses)} ({share(s.cash_expenses):.0f}%)",
    ]
    return [f"GASTOS POR MÉTODO DE PAGO: {'; '.join(parts)}"]


def _format_snapshot(s: FinancialSnapshot) -> str:
    """Render the snapshot as grounded facts for the LLM to reason over."""
    lines = [f"Situación financiera ({period_label(s.period)}):"]

    # The base income is a fallback, not additive: report the effective income so
    # the LLM never sees a contradictory "base + registrados = total" line.
    if s.income_registered > 0:
        lines.append(f"INGRESOS: {_money(s.total_income)} (registrados este mes)")
    elif s.income_base > 0:
        lines.append(
            f"INGRESOS: {_money(s.total_income)} "
            "(ingreso base de referencia; sin ingresos registrados este mes)"
        )
    else:
        lines.append(f"INGRESOS: {_money(s.total_income)}")
    lines.append(f"GASTOS: {_money(s.total_expenses)}")
    lines.extend(_payment_split_lines(s))
    lines.append(f"DISPONIBLE (ingresos - gastos): {_money(s.disposable)}")
    if s.savings_target_amount is not None and s.savings_target_pct is not None:
        lines.append(
            f"META DE AHORRO: {s.savings_target_pct:.0f}% = "
            f"{_money(s.savings_target_amount)} al mes"
        )

    if s.by_category:
        cats = "; ".join(
            f"{get_category_label(c.category)} {_money(c.amount)} "
            f"({c.percentage:.0f}%)"
            for c in s.by_category
        )
        lines.append(f"GASTOS POR CATEGORÍA: {cats}")

    if s.budgets:
        buds = "; ".join(
            f"{get_category_label(b.category) if b.category else b.name} "
            f"{_money(b.spent)}/{_money(b.limit)} ({b.percentage:.0f}%)"
            for b in s.budgets
        )
        lines.append(f"PRESUPUESTOS: {buds}")

    if s.goals:
        goals = "; ".join(
            f"{g.name} {_money(g.current)}/{_money(g.target)} ({g.percentage:.0f}%)"
            for g in s.goals
        )
        lines.append(f"METAS DE AHORRO: {goals}")

    if s.cards:
        cards = "; ".join(
            f"{c.name} deuda {_money(c.balance)} de {_money(c.limit)} "
            f"(disponible {_money(c.available)}, próximo pago {c.next_payment_date})"
            for c in s.cards
        )
        lines.append(
            f"TARJETAS: deuda total {_money(s.card_debt_total)}, disponible "
            f"{_money(s.card_available_total)}. {cards}"
        )

    return "\n".join(lines)
