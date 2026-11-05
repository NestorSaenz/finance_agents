"""Budget tools for conversational data operations.

Thin wrappers over ``BudgetService`` exposed to the LLM as callable tools.

Security: ``user_id`` is supplied by the toolkit from the authenticated context
at dispatch time and is NEVER part of the tool schema nor read from the model's
arguments.
"""

import asyncio
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from pydantic import ValidationError

from app.agents.tools.names import (
    CREATE_BUDGET_TOOL,
    DELETE_BUDGET_TOOL,
    QUERY_BUDGETS_TOOL,
    UPDATE_BUDGET_TOOL,
)
from app.core.exceptions import BudgetNotFoundError
from app.core.logging import get_logger
from app.shared.clock import current_today
from app.shared.types import BudgetPeriod, UserId, normalize_category
from app.src.budgets.constants import MAX_PAGE_SIZE
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.budgets.models import Budget, BudgetCreate, BudgetStatus

logger = get_logger(__name__)

# Status reads per query run concurrently, bounded so a big list can't flood the DB pool.
_STATUS_CONCURRENCY: Final[int] = 8
_PERIOD_LABELS: Final[dict[BudgetPeriod, str]] = {
    BudgetPeriod.WEEKLY: "semanal",
    BudgetPeriod.MONTHLY: "mensual",
    BudgetPeriod.YEARLY: "anual",
}


BUDGET_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": CREATE_BUDGET_TOOL,
            "description": (
                "Crea un presupuesto (límite de gasto) para el usuario. Úsala cuando "
                "el usuario quiere fijar un tope de gasto, por categoría o general."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre del presupuesto"},
                    "amount": {"type": "number", "description": "Límite, mayor a 0"},
                    "category": {
                        "type": "string",
                        "description": "Categoría opcional; si se omite, es un presupuesto general",
                    },
                    "period_type": {
                        "type": "string",
                        "enum": ["weekly", "monthly", "yearly"],
                        "description": "Periodo del presupuesto (por defecto mensual)",
                    },
                },
                "required": ["name", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": QUERY_BUDGETS_TOOL,
            "description": (
                "Consulta los presupuestos del usuario y cuánto ha gastado en cada uno "
                "(gastado, restante y porcentaje). El gastado INCLUYE los gastos fijos "
                "(recurrentes); la alerta ⚠️ avisa si los gastos variables se acercan al "
                "tope o si ya se pasó. Úsala para '¿cómo van mis presupuestos?'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": UPDATE_BUDGET_TOOL,
            "description": (
                "Cambia un presupuesto existente (p. ej. subir o bajar el tope). Lo "
                "identificas por su NOMBRE o CATEGORÍA (ej. 'alimentación'); el sistema "
                "lo encuentra — tú NO manejas ids. Úsala tras confirmar el cambio con "
                "el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {
                        "type": "string",
                        "description": "Nombre o categoría del presupuesto (ej. 'alimentación')",
                    },
                    "new_amount": {
                        "type": "number",
                        "description": "Nuevo tope, mayor a 0 (opcional)",
                    },
                    "new_name": {"type": "string", "description": "Nuevo nombre (opcional)"},
                },
                "required": ["reference"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": DELETE_BUDGET_TOOL,
            "description": (
                "Elimina un presupuesto existente. Lo identificas por su NOMBRE o "
                "CATEGORÍA; el sistema lo encuentra — tú NO manejas ids. Úsala tras "
                "confirmar con el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reference": {
                        "type": "string",
                        "description": "Nombre o categoría del presupuesto a eliminar",
                    },
                },
                "required": ["reference"],
            },
        },
    },
]


class BudgetToolkit:
    """Exposes budget tools to the LLM and dispatches its tool calls."""

    def __init__(self, service: BudgetServiceABC) -> None:
        self._service = service

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return BUDGET_TOOL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        if name == CREATE_BUDGET_TOOL:
            return await self._create(arguments, user_id)
        if name == QUERY_BUDGETS_TOOL:
            return await self._query(user_id)
        if name == UPDATE_BUDGET_TOOL:
            return await self._update(arguments, user_id)
        if name == DELETE_BUDGET_TOOL:
            return await self._delete(arguments, user_id)
        raise ValueError(f"Unknown budget tool: {name}")

    async def _create(self, args: dict[str, Any], user_id: UserId) -> str:
        try:
            budget = BudgetCreate(
                name=str(args.get("name", "")).strip(),
                amount=_to_decimal(args.get("amount")),
                category=_to_category(args.get("category")),
                period_type=_to_period(args.get("period_type")),
                start_date=current_today(),
            )
        except (ValidationError, ValueError) as e:
            logger.warning("Invalid budget args from tool", error=str(e))
            return "No pude crear el presupuesto: revisa el nombre y el monto (mayor a 0)."

        # If a tope for this category already exists, UPDATE it instead of creating a
        # duplicate ("el presupuesto de transporte va a ser 349.300" must not spawn a
        # second 'transporte' budget). Matches deterministically by category.
        if budget.category:
            existing = await self._service.resolve_budget(budget.category, user_id)
            if existing is not None and existing.category == budget.category:
                updated = await self._service.update_budget(
                    existing.id, user_id, amount=budget.amount
                )
                return (
                    f"✏️ Ya tenías un tope de {budget.category}; lo actualicé a "
                    f"${updated.amount} (no creé uno nuevo)."
                )

        created = await self._service.create_budget(budget, user_id)
        scope = created.category if created.category else "general"
        return (
            f"✅ Presupuesto creado: {created.name} — ${created.amount} "
            f"({scope}, {created.period_type.value})."
        )

    async def _list_all(self, user_id: UserId) -> tuple[list[Budget], int]:
        """Every active budget (paging through the service) and the service's total count."""
        budgets: list[Budget] = []
        page = 1
        while True:
            items, total = await self._service.list_budgets(
                user_id, page=page, page_size=MAX_PAGE_SIZE
            )
            budgets.extend(items)
            if not items or len(budgets) >= total:
                return budgets, total
            page += 1

    async def _status_or_none(
        self, budget: Budget, user_id: UserId, gate: asyncio.Semaphore
    ) -> BudgetStatus | None:
        """The budget's status, or ``None`` when it could not be read (logged)."""
        async with gate:
            try:
                return await self._service.get_budget_status(
                    budget.id, user_id, as_of=current_today()
                )
            except Exception as e:  # noqa: BLE001 - one budget failing shouldn't drop the rest.
                logger.warning("Budget status failed", budget_id=budget.id, error=str(e))
                return None

    async def _query(self, user_id: UserId) -> str:
        budgets, total = await self._list_all(user_id)
        if not budgets:
            return "No tienes presupuestos configurados."

        gate = asyncio.Semaphore(_STATUS_CONCURRENCY)
        # gather keeps the input order, so failed budgets stay where they were listed.
        statuses = await asyncio.gather(
            *[self._status_or_none(budget, user_id, gate) for budget in budgets]
        )
        entries = list(zip(budgets, statuses, strict=True))
        lines = [
            _format_status(status) if status else f"- {budget.name}: límite ${budget.amount}"
            for budget, status in entries
        ]
        report = [f"{total} presupuesto(s):", *lines, *_format_totals(entries)]
        if len(budgets) != total:
            report.append(
                f"Ojo: solo pude leer {len(budgets)} de {total} presupuestos; los totales no "
                "los incluyen todos."
            )
        return "\n".join(report)

    async def _update(self, args: dict[str, Any], user_id: UserId) -> str:
        reference = str(args.get("reference", "")).strip()
        budget = await self._service.resolve_budget(reference, user_id)
        if budget is None:
            return f"No encontré un presupuesto para '{reference}'. ¿Cuál quieres cambiar?"

        new_amount = _opt_decimal(args.get("new_amount"))
        new_name = _opt_str(args.get("new_name"))
        if new_amount is None and new_name is None:
            return "¿Qué quieres cambiar del presupuesto: el tope o el nombre?"
        if new_amount is not None and new_amount <= 0:
            return "El nuevo tope debe ser mayor a 0."

        try:
            updated = await self._service.update_budget(
                budget.id, user_id, name=new_name, amount=new_amount
            )
        except BudgetNotFoundError:
            return "No encontré ese presupuesto para actualizar."
        scope = updated.category if updated.category else "general"
        return f"✏️ Actualicé el presupuesto {updated.name} — ${updated.amount} ({scope})."

    async def _delete(self, args: dict[str, Any], user_id: UserId) -> str:
        reference = str(args.get("reference", "")).strip()
        budget = await self._service.resolve_budget(reference, user_id)
        if budget is None:
            return f"No encontré un presupuesto para '{reference}'."
        try:
            deleted = await self._service.delete_budget(budget.id, user_id)
        except BudgetNotFoundError:
            return "No encontré ese presupuesto (quizás ya no existe)."
        return f"🗑️ Eliminé el presupuesto {deleted.name}."


_Entry = tuple[Budget, BudgetStatus | None]


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _format_totals(entries: list[_Entry]) -> list[str]:
    """TOTAL lines, summed here in Decimal so the model never adds amounts itself.

    One group per (currency, period): amounts of different periods or currencies are
    never mixed. Inside a group only the CATEGORY budgets are totalled: the overall
    ("general") budget already covers every expense, so adding it would double count;
    it is shown on its own line. A budget whose status failed still counts in the
    topes; its spending is unknown, so ``gastado``/``restan`` cover the others only.
    """
    groups: dict[tuple[str, BudgetPeriod], list[_Entry]] = defaultdict(list)
    for entry in entries:
        budget = entry[0]
        groups[(budget.currency.value, budget.period_type)].append(entry)

    lines: list[str] = []
    for (currency, period), group in groups.items():
        label = "" if len(groups) == 1 else f" {_PERIOD_LABELS[period]} ({currency})"
        by_category = [e for e in group if e[0].category]
        if by_category:
            lines.append(_category_total(by_category, label))
        lines.extend(_general_line(e, label) for e in group if not e[0].category)
    return lines


def _category_total(group: list[_Entry], label: str) -> str:
    topes = sum((b.amount for b, _ in group), Decimal("0"))
    known = [s for _, s in group if s is not None]
    unavailable = [b for b, s in group if s is None]
    spent = sum((s.spent for s in known), Decimal("0"))
    remaining = sum((s.remaining for s in known), Decimal("0"))
    left = f"restan ${remaining}" if remaining >= 0 else f"te pasaste por ${-remaining}"
    count = _plural(len(group), "presupuesto", "presupuestos")
    over = sum(1 for s in known if s.remaining < 0)
    # The net "restan" hides overspent budgets, so say how many went over.
    overspent = f" ({_plural(over, 'pasado', 'pasados')})" if over else ""
    head = f"TOTAL{label} (por categoría): topes ${topes}"
    if not unavailable:
        return f"{head} · gastado ${spent} · {left} ({count}){overspent}"
    names = ", ".join(b.name for b in unavailable)
    return (
        f"{head} ({count}) · gastado ${spent} · {left} "
        f"(solo de los {len(known)} con datos; sin datos de gasto: {names}){overspent}"
    )


def _general_line(entry: _Entry, label: str) -> str:
    budget, status = entry
    spent = f"gastado ${status.spent}" if status else "sin datos de gasto"
    return f"General{label}: tope ${budget.amount} · {spent}"


def _format_status(status: BudgetStatus) -> str:
    """Format a budget's spending status for the LLM."""
    budget = status.budget
    scope = budget.category if budget.category else "general"
    alert = " ⚠️" if status.alert_triggered else ""
    fixed = f" (incluye ${status.spent_fixed} en fijos)" if status.spent_fixed > 0 else ""
    left = (
        f"restan ${status.remaining}"
        if status.remaining >= 0
        else f"te pasaste por ${-status.remaining}"
    )
    return (
        f"- {budget.name} ({scope}): gastado ${status.spent}{fixed} de ${budget.amount} "
        f"({status.percentage:.0f}%), {left}{alert}"
    )


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"Invalid amount: {value!r}") from e


def _opt_decimal(value: Any) -> Decimal | None:
    """Parse an optional amount for updates; ``None`` means 'leave unchanged'."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _opt_str(value: Any) -> str | None:
    if not value:
        return None
    return str(value).strip() or None


def _to_category(value: Any) -> str | None:
    # Known or custom: normalize and pass through (a None/empty means "overall").
    if not value:
        return None
    return normalize_category(str(value))


def _to_period(value: Any) -> BudgetPeriod:
    if not value:
        return BudgetPeriod.MONTHLY
    try:
        return BudgetPeriod(str(value).lower())
    except ValueError:
        return BudgetPeriod.MONTHLY
