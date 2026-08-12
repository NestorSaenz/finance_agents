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
from app.src.analysis.interfaces import AnalysisServiceABC
from app.src.analysis.models import FinancialSnapshot

logger = get_logger(__name__)

ANALYZE_FINANCES_TOOL = "analyze_finances"

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
    }
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
        raise ValueError(f"Unknown analysis tool: {name}")


def _money(value: Decimal) -> str:
    """Format an amount with thousands separators and no decimals (pesos)."""
    return f"${value:,.0f}"


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
