"""Budget tools for conversational data operations.

Thin wrappers over ``BudgetService`` exposed to the LLM as callable tools.

Security: ``user_id`` is supplied by the toolkit from the authenticated context
at dispatch time and is NEVER part of the tool schema nor read from the model's
arguments.
"""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import BudgetNotFoundError
from app.core.logging import get_logger
from app.shared.types import BudgetPeriod, UserId, normalize_category
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.budgets.models import BudgetCreate, BudgetStatus

logger = get_logger(__name__)

CREATE_BUDGET_TOOL = "create_budget"
QUERY_BUDGETS_TOOL = "query_budgets"
UPDATE_BUDGET_TOOL = "update_budget"
DELETE_BUDGET_TOOL = "delete_budget"

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
                "(gastado, restante y porcentaje). Úsala para '¿cómo van mis presupuestos?'."
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
                start_date=datetime.now(UTC).date(),
            )
        except (ValidationError, ValueError) as e:
            logger.warning("Invalid budget args from tool", error=str(e))
            return "No pude crear el presupuesto: revisa el nombre y el monto (mayor a 0)."

        created = await self._service.create_budget(budget, user_id)
        scope = created.category if created.category else "general"
        return (
            f"✅ Presupuesto creado: {created.name} — ${created.amount} "
            f"({scope}, {created.period_type.value})."
        )

    async def _query(self, user_id: UserId) -> str:
        budgets, total = await self._service.list_budgets(user_id, page=1, page_size=20)
        if not budgets:
            return "No tienes presupuestos configurados."

        lines: list[str] = []
        for budget in budgets:
            try:
                status = await self._service.get_budget_status(budget.id, user_id)
                lines.append(_format_status(status))
            except Exception as e:  # noqa: BLE001 - one budget failing shouldn't drop the rest.
                logger.warning("Budget status failed", budget_id=budget.id, error=str(e))
                lines.append(f"- {budget.name}: límite ${budget.amount}")
        return f"{total} presupuesto(s):\n" + "\n".join(lines)

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


def _format_status(status: BudgetStatus) -> str:
    """Format a budget's spending status for the LLM."""
    budget = status.budget
    scope = budget.category if budget.category else "general"
    alert = " ⚠️" if status.alert_triggered else ""
    return (
        f"- {budget.name} ({scope}): gastado ${status.spent} de ${budget.amount} "
        f"({status.percentage:.0f}%), restan ${status.remaining}{alert}"
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
