"""Credit-card tools for conversational data operations.

Thin wrappers over ``CreditCardService`` exposed to the LLM. ``user_id`` is
supplied by the toolkit from the authenticated context at dispatch time and is
NEVER part of the tool schema. Cards are referenced by NAME (no ids exposed).
"""

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import CardNotFoundError
from app.core.logging import get_logger
from app.shared.types import UserId
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import CardPaymentCreate, CreditCardCreate

logger = get_logger(__name__)

CREATE_CARD_TOOL = "create_card"
QUERY_CARDS_TOOL = "query_cards"
PAY_CARD_TOOL = "pay_card"
UPDATE_CARD_TOOL = "update_card"
DELETE_CARD_TOOL = "delete_card"

CARD_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": CREATE_CARD_TOOL,
            "description": (
                "Registra una tarjeta de crédito del usuario. Úsala cuando quiere "
                "agregar/registrar una tarjeta. Solo se guarda el nombre (no números)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre de la tarjeta (ej. Visa BBVA)"},
                    "credit_limit": {"type": "number", "description": "Cupo/límite, mayor a 0"},
                    "cutoff_day": {"type": "integer", "description": "Día de corte (1-31)"},
                    "payment_day": {"type": "integer", "description": "Día de pago (1-31)"},
                },
                "required": ["name", "credit_limit", "cutoff_day", "payment_day"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": QUERY_CARDS_TOOL,
            "description": (
                "Consulta las tarjetas del usuario: gastado en el ciclo, deuda actual, "
                "crédito disponible y próxima fecha de pago. Úsala para '¿cómo van mis "
                "tarjetas?' o '¿cuánto llevo en la tarjeta?'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": PAY_CARD_TOOL,
            "description": (
                "Registra un pago/abono hecho a una tarjeta de crédito (reduce la deuda). "
                "Úsala cuando el usuario dice que pagó o abonó a su tarjeta."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {"type": "string", "description": "Nombre de la tarjeta"},
                    "amount": {"type": "number", "description": "Monto pagado, mayor a 0"},
                    "payment_date": {
                        "type": "string",
                        "description": (
                            "Fecha del pago YYYY-MM-DD si el usuario la indica "
                            "(p. ej. 'pagué el 1 de julio'); por defecto, hoy."
                        ),
                    },
                },
                "required": ["card_name", "amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": UPDATE_CARD_TOOL,
            "description": (
                "Cambia los datos de una tarjeta existente (nombre, cupo, día de corte "
                "o de pago). La identificas por su NOMBRE actual; el sistema la "
                "encuentra. Úsala tras confirmar el cambio con el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {"type": "string", "description": "Nombre actual de la tarjeta"},
                    "new_name": {"type": "string", "description": "Nuevo nombre (opcional)"},
                    "new_credit_limit": {
                        "type": "number",
                        "description": "Nuevo cupo/límite, mayor a 0 (opcional)",
                    },
                    "new_cutoff_day": {
                        "type": "integer",
                        "description": "Nuevo día de corte, 1-31 (opcional)",
                    },
                    "new_payment_day": {
                        "type": "integer",
                        "description": "Nuevo día de pago, 1-31 (opcional)",
                    },
                },
                "required": ["card_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": DELETE_CARD_TOOL,
            "description": (
                "Elimina (desactiva) una tarjeta existente. La identificas por su "
                "NOMBRE. Su historial de gastos y pagos se conserva. Úsala tras "
                "confirmar con el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {"type": "string", "description": "Nombre de la tarjeta a eliminar"},
                },
                "required": ["card_name"],
            },
        },
    },
]


class CardToolkit:
    """Exposes credit-card tools to the LLM and dispatches its tool calls."""

    def __init__(self, service: CreditCardServiceABC) -> None:
        self._service = service

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return CARD_TOOL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        if name == CREATE_CARD_TOOL:
            return await self._create(arguments, user_id)
        if name == QUERY_CARDS_TOOL:
            return await self._query(user_id)
        if name == PAY_CARD_TOOL:
            return await self._pay(arguments, user_id)
        if name == UPDATE_CARD_TOOL:
            return await self._update(arguments, user_id)
        if name == DELETE_CARD_TOOL:
            return await self._delete(arguments, user_id)
        raise ValueError(f"Unknown card tool: {name}")

    async def _create(self, args: dict[str, Any], user_id: UserId) -> str:
        try:
            card = CreditCardCreate(
                name=str(args.get("name", "")).strip(),
                credit_limit=_to_decimal(args.get("credit_limit")),
                cutoff_day=int(args.get("cutoff_day", 0)),
                payment_day=int(args.get("payment_day", 0)),
            )
        except (ValidationError, ValueError, TypeError) as e:
            logger.warning("Invalid card args from tool", error=str(e))
            return (
                "No pude registrar la tarjeta: revisa el nombre, el límite (mayor a 0) "
                "y que los días de corte y pago estén entre 1 y 31."
            )

        created = await self._service.create_card(card, user_id)
        return (
            f"✅ Registré tu tarjeta {created.name} — cupo ${created.credit_limit}, "
            f"corte día {created.cutoff_day}, pago día {created.payment_day}."
        )

    async def _query(self, user_id: UserId) -> str:
        statuses = await self._service.get_all_status(user_id)
        if not statuses:
            return "No tienes tarjetas registradas."
        lines = [
            f"- {s.card.name}: deuda ${s.balance} de ${s.card.credit_limit} "
            f"(disponible ${s.available}); gastado este ciclo ${s.spent_cycle}; "
            f"próximo pago {s.next_payment_date}"
            for s in statuses
        ]
        return f"{len(statuses)} tarjeta(s):\n" + "\n".join(lines)

    async def _pay(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("card_name", "")).strip()
        try:
            amount = _to_decimal(args.get("amount"))
        except ValueError:
            return "No pude registrar el pago: el monto no es válido."
        if amount <= 0:
            return "El monto del pago debe ser mayor a 0."

        card = await self._service.resolve_by_name(name, user_id)
        if card is None:
            return f"No encontré una tarjeta llamada '{name}'. ¿Puedes indicar el nombre exacto?"

        # Honor the date the user stated ("pagué el 1 de julio"); default to today.
        today = datetime.now(UTC).date()
        payment_date = _opt_date(args.get("payment_date")) or today
        await self._service.register_payment(
            card.id, user_id, CardPaymentCreate(amount=amount, payment_date=payment_date)
        )
        when = "" if payment_date == today else f" ({payment_date})"
        return f"✅ Registré tu pago de ${amount} a '{card.name}'{when}."

    async def _update(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("card_name", "")).strip()
        card = await self._service.resolve_by_name(name, user_id)
        if card is None:
            return f"No encontré una tarjeta llamada '{name}'. ¿Cuál es el nombre exacto?"

        new_name = _opt_str(args.get("new_name"))
        new_limit = _opt_decimal(args.get("new_credit_limit"))
        new_cutoff = _opt_day(args.get("new_cutoff_day"))
        new_payment = _opt_day(args.get("new_payment_day"))
        if new_name is None and new_limit is None and new_cutoff is None and new_payment is None:
            return "¿Qué quieres cambiar de la tarjeta: el nombre, el cupo o los días de corte/pago?"
        if new_limit is not None and new_limit <= 0:
            return "El nuevo cupo debe ser mayor a 0."

        try:
            updated = await self._service.update_card(
                card.id,
                user_id,
                name=new_name,
                credit_limit=new_limit,
                cutoff_day=new_cutoff,
                payment_day=new_payment,
            )
        except CardNotFoundError:
            return "No encontré esa tarjeta para actualizar."
        return (
            f"✏️ Actualicé tu tarjeta {updated.name} — cupo ${updated.credit_limit}, "
            f"corte día {updated.cutoff_day}, pago día {updated.payment_day}."
        )

    async def _delete(self, args: dict[str, Any], user_id: UserId) -> str:
        name = str(args.get("card_name", "")).strip()
        card = await self._service.resolve_by_name(name, user_id)
        if card is None:
            return f"No encontré una tarjeta llamada '{name}'."
        try:
            deleted = await self._service.delete_card(card.id, user_id)
        except CardNotFoundError:
            return "No encontré esa tarjeta (quizás ya no existe)."
        return f"🗑️ Eliminé tu tarjeta {deleted.name}. Su historial de gastos se conserva."


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"Invalid amount: {value!r}") from e


def _opt_str(value: Any) -> str | None:
    if not value:
        return None
    return str(value).strip() or None


def _opt_date(value: Any) -> date | None:
    """Parse a 'YYYY-MM-DD' string to a date, or None if absent/invalid."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _opt_decimal(value: Any) -> Decimal | None:
    """Parse an optional amount for updates; ``None`` means 'leave unchanged'."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _opt_day(value: Any) -> int | None:
    """Parse an optional day-of-month (1-31); ``None`` means 'leave unchanged'."""
    if value is None:
        return None
    try:
        day = int(value)
    except (TypeError, ValueError):
        return None
    return day if 1 <= day <= 31 else None
