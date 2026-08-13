"""Movement-search tool for conversational data operations.

Thin wrapper over ``MovementFinder`` exposed to the LLM. It unifies the three
ledgers (transactions, card payments, goal contributions) behind ONE search, so
when the user says "borra el movimiento de $X" the agent can locate it whatever
its kind and route deletion to the right tool. ``user_id`` is supplied by the
toolkit from the authenticated context at dispatch time, NEVER by the model.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from app.core.logging import get_logger
from app.shared.clock import current_today
from app.shared.types import MovementKind, UserId
from app.src.analysis.interfaces import MovementFinderServiceABC
from app.src.analysis.models import MovementCandidate

logger = get_logger(__name__)

FIND_MOVEMENTS_TOOL = "find_movements"

# Cap on candidates listed back (the count still reflects everything found).
_DISPLAY_LIMIT: Final[int] = 15

# How each kind reads to the user, and which tool deletes it.
_KIND_LABEL: Final[dict[MovementKind, str]] = {
    MovementKind.EXPENSE: "gasto",
    MovementKind.INCOME: "ingreso",
    MovementKind.CARD_PAYMENT: "pago de tarjeta",
    MovementKind.GOAL_CONTRIBUTION: "aporte a meta",
    MovementKind.GOAL_WITHDRAWAL: "retiro de meta",
}

# Routing hint appended to results: results feed back as plain text, so telling
# the agent which tool matches each kind keeps deletion grounded and provider-
# agnostic (the system prompt carries the same mapping).
_ROUTING_HINT: Final[str] = (
    "\n\nConfirma con el usuario CUÁL borrar y usa la herramienta que corresponda al tipo:\n"
    "- gasto/ingreso → delete_transaction (description, amount, transaction_date)\n"
    "- aporte a meta → remove_goal_contribution (goal_name, amount, date)\n"
    "- pago de tarjeta → remove_card_payment (card_name, amount, payment_date)\n"
    "- retiro de meta → pregúntale al usuario qué desea hacer (un retiro se deshace "
    "volviendo a aportar con contribute_to_goal)."
)

MOVEMENT_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": FIND_MOVEMENTS_TOOL,
            "description": (
                "Busca un movimiento del usuario en TODAS sus fuentes a la vez: "
                "gastos/ingresos, pagos de tarjeta y aportes/retiros de metas. Úsala "
                "como PASO PREVIO cuando el usuario quiere BORRAR o CORREGIR 'un "
                "movimiento' y NO sabes de qué tipo es (p. ej. 'borra el movimiento de "
                "8.9M del 12 de agosto', 'quita ese aporte'). Filtra por monto, fecha "
                "y/o texto. Muestra lo que encontró, CONFIRMA con el usuario y luego "
                "bórralo con la herramienta correcta según el tipo. Si delete_transaction "
                "no encuentra un movimiento, NO concluyas que no existe: puede ser un "
                "pago de tarjeta o un aporte a meta; búscalo aquí."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Monto del movimiento a buscar (mayor a 0)",
                    },
                    "date": {
                        "type": "string",
                        "description": (
                            "Fecha del movimiento YYYY-MM-DD si el usuario la indica"
                        ),
                    },
                    "text": {
                        "type": "string",
                        "description": (
                            "Texto para acotar: descripción del gasto, o el nombre de la "
                            "meta/tarjeta/categoría (p. ej. 'emergencia', 'Nu')"
                        ),
                    },
                },
            },
        },
    },
]


class MovementToolkit:
    """Exposes the unified movement-search tool to the LLM."""

    def __init__(self, finder: MovementFinderServiceABC) -> None:
        self._finder = finder

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return MOVEMENT_TOOL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        if name == FIND_MOVEMENTS_TOOL:
            return await self._find(arguments, user_id)
        raise ValueError(f"Unknown movement tool: {name}")

    async def _find(self, args: dict[str, Any], user_id: UserId) -> str:
        amount = _opt_decimal(args.get("amount"))
        on_date = _opt_date(args.get("date"))
        text = _opt_str(args.get("text"))
        if amount is None and on_date is None and text is None:
            return "¿Qué movimiento busco? Dame el monto, la fecha o una descripción."

        candidates = await self._finder.find_movements(
            user_id, amount=amount, on_date=on_date, text=text, today=current_today()
        )
        if not candidates:
            return (
                "No encontré ningún movimiento con esos datos. Revisa el monto, la "
                "fecha o la descripción."
            )
        logger.info("Found movements", count=len(candidates), user_id=user_id)
        shown = candidates[:_DISPLAY_LIMIT]
        lines = "\n".join(_format_candidate(c) for c in shown)
        capped = (
            f" (muestro los {_DISPLAY_LIMIT} más recientes)"
            if len(candidates) > _DISPLAY_LIMIT
            else ""
        )
        header = f"Encontré {len(candidates)} movimiento(s){capped}:"
        return f"{header}\n{lines}{_ROUTING_HINT}"


def _format_candidate(candidate: MovementCandidate) -> str:
    return (
        f"- {_KIND_LABEL[candidate.kind]} «{candidate.label}»: "
        f"${candidate.amount:,.0f} ({candidate.date})"
    )


def _opt_decimal(value: Any) -> Decimal | None:
    """Parse an optional positive amount; None/invalid/≤0 yields None."""
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return amount if amount > 0 else None


def _opt_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _opt_str(value: Any) -> str | None:
    if not value:
        return None
    return str(value).strip() or None
