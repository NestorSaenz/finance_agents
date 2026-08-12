"""Recurring-transaction tools for conversational data operations.

Thin wrappers over ``RecurringService`` exposed to the LLM as callable tools.

Security: ``user_id`` is supplied by the toolkit from the authenticated context
at dispatch time and is NEVER part of the tool schema nor read from the model's
arguments. Templates are identified by their DESCRIPTION (resolved to an id
server-side) so the model never handles internal ids.
"""

from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.core.logging import get_logger
from app.shared.types import PaymentMethod, TransactionType, UserId, normalize_category
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import CreditCard
from app.src.recurring.interfaces import RecurringServiceABC
from app.src.recurring.models import (
    RecurringCreate,
    RecurringFrequency,
    RecurringTransaction,
    RecurringUpdate,
)

logger = get_logger(__name__)

CREATE_RECURRING_TOOL = "create_recurring"
LIST_RECURRING_TOOL = "list_recurring"
UPDATE_RECURRING_TOOL = "update_recurring"
DELETE_RECURRING_TOOL = "delete_recurring"
PAUSE_RECURRING_TOOL = "pause_recurring"
RESUME_RECURRING_TOOL = "resume_recurring"

RECURRING_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": CREATE_RECURRING_TOOL,
            "description": (
                "Crea un movimiento RECURRENTE mensual (una plantilla que se registra "
                "sola cada mes): sueldo, arriendo, suscripciones. Úsala cuando el usuario "
                "dice que CADA MES paga o recibe algo un día fijo (p. ej. 'cada mes pago "
                "50 mil de Netflix el día 5', 'todos los meses recibo mi sueldo el 30'). "
                "NO la uses para un gasto puntual (eso es register_transaction)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Monto por mes, mayor a 0"},
                    "description": {
                        "type": "string",
                        "description": "Nombre del recurrente (p. ej. 'Netflix', 'Arriendo', 'Sueldo')",
                    },
                    "transaction_type": {
                        "type": "string",
                        "enum": ["income", "expense"],
                        "description": "Tipo: ingreso (income) o gasto (expense)",
                    },
                    "day_of_month": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 31,
                        "description": "Día del mes en que ocurre (1-31)",
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Categoría del gasto (opcional): pásala si el usuario la nombra "
                            "o dedúcela de la descripción."
                        ),
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["efectivo", "credito"],
                        "description": (
                            "Método de pago SOLO si el usuario lo menciona: 'credito' para "
                            "tarjeta de crédito, 'efectivo' para efectivo/débito/transferencia."
                        ),
                    },
                    "card_name": {
                        "type": "string",
                        "description": (
                            "Nombre de la tarjeta si el recurrente es a CRÉDITO. Pásalo "
                            "EXACTAMENTE como lo escribió el usuario; se busca por coincidencia "
                            "parcial. Un recurrente a crédito DEBE ir vinculado a una tarjeta."
                        ),
                    },
                    "frequency": {
                        "type": "string",
                        "enum": ["monthly"],
                        "description": "Frecuencia (por ahora solo mensual)",
                    },
                },
                "required": ["amount", "description", "transaction_type", "day_of_month"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": LIST_RECURRING_TOOL,
            "description": (
                "Lista los movimientos recurrentes del usuario (descripción, monto, día del "
                "mes, próximo registro y si está activo o pausado). Úsala para '¿qué "
                "recurrentes tengo?', '¿qué se me cobra cada mes?'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": UPDATE_RECURRING_TOOL,
            "description": (
                "Cambia los datos de un recurrente existente (identificado por su "
                "DESCRIPCIÓN): nombre, monto, tipo (ingreso/gasto), día del mes, "
                "categoría, método de pago o tarjeta. NO manejas ids: el sistema lo "
                "encuentra por la descripción."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Descripción ACTUAL del recurrente a cambiar (p. ej. 'Netflix')",
                    },
                    "new_description": {
                        "type": "string",
                        "description": "Nuevo nombre/descripción del recurrente (para renombrarlo, opcional)",
                    },
                    "new_amount": {"type": "number", "description": "Nuevo monto (opcional)"},
                    "new_type": {
                        "type": "string",
                        "enum": ["income", "expense"],
                        "description": "Nuevo tipo: ingreso (income) o gasto (expense) (opcional)",
                    },
                    "new_day_of_month": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 31,
                        "description": "Nuevo día del mes (opcional)",
                    },
                    "new_category": {"type": "string", "description": "Nueva categoría (opcional)"},
                    "payment_method": {
                        "type": "string",
                        "enum": ["efectivo", "credito"],
                        "description": (
                            "Nuevo método de pago (opcional). 'efectivo' desvincula la "
                            "tarjeta; 'credito' requiere una tarjeta (se pregunta si falta)."
                        ),
                    },
                    "card_name": {
                        "type": "string",
                        "description": "Nueva tarjeta si pasa a crédito o para revincular (opcional)",
                    },
                    "unlink_card": {
                        "type": "boolean",
                        "description": "Pon true para DESVINCULAR la tarjeta del recurrente (opcional)",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": DELETE_RECURRING_TOOL,
            "description": (
                "Elimina un recurrente (identificado por su DESCRIPCIÓN). Destructivo: "
                "confírmalo con el usuario y ejecútalo SOLO tras su 'sí'. Los movimientos "
                "ya registrados se conservan; solo deja de registrarse a futuro."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Descripción del recurrente a eliminar",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": PAUSE_RECURRING_TOOL,
            "description": (
                "Pausa un recurrente (identificado por su DESCRIPCIÓN): deja de registrarse "
                "cada mes hasta que se reanude. Úsala para 'pausa/suspende mi recurrente X'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Descripción del recurrente a pausar",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": RESUME_RECURRING_TOOL,
            "description": (
                "Reanuda un recurrente pausado (identificado por su DESCRIPCIÓN): vuelve a "
                "registrarse cada mes. Úsala para 'reactiva/reanuda mi recurrente X'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Descripción del recurrente a reanudar",
                    },
                },
                "required": ["description"],
            },
        },
    },
]


class RecurringToolkit:
    """Exposes recurring-transaction tools to the LLM and dispatches its calls.

    The toolkit wraps ``RecurringService``; it contains no business logic itself.
    """

    def __init__(
        self,
        service: RecurringServiceABC,
        cards: CreditCardServiceABC | None = None,
    ) -> None:
        self._service = service
        # Optional: resolves a credit recurrente to a specific card by name.
        self._cards = cards

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return RECURRING_TOOL_SCHEMAS

    async def dispatch(
        self, name: str, arguments: dict[str, Any], user_id: UserId
    ) -> str:
        if name == CREATE_RECURRING_TOOL:
            return await self._create(arguments, user_id)
        if name == LIST_RECURRING_TOOL:
            return await self._list(user_id)
        if name == UPDATE_RECURRING_TOOL:
            return await self._update(arguments, user_id)
        if name == DELETE_RECURRING_TOOL:
            return await self._delete(arguments, user_id)
        if name == PAUSE_RECURRING_TOOL:
            return await self._set_active(arguments, user_id, active=False)
        if name == RESUME_RECURRING_TOOL:
            return await self._set_active(arguments, user_id, active=True)
        raise ValueError(f"Unknown recurring tool: {name}")

    async def _create(self, args: dict[str, Any], user_id: UserId) -> str:
        payment_method = _to_payment_method(args.get("payment_method"))
        card, clarification = await self._resolve_card(args, payment_method, user_id)
        if clarification is not None:
            return clarification
        # A recurrente linked to a card is on credit by definition.
        if card is not None:
            payment_method = PaymentMethod.CREDITO

        category = _to_category(args.get("category"))
        try:
            rec = RecurringCreate(
                amount=_to_decimal(args.get("amount")),
                description=str(args.get("description", "")).strip(),
                transaction_type=TransactionType(args.get("transaction_type", "expense")),
                category=category,
                payment_method=payment_method,
                card_id=card.id if card else None,
                frequency=_to_frequency(args.get("frequency")),
                day_of_month=_to_int(args.get("day_of_month")),
            )
        except (ValidationError, ValueError) as e:
            logger.warning("Invalid recurring args from tool", error=str(e))
            return (
                "No pude crear el recurrente: revisa el monto (mayor a 0), el tipo y "
                "el día del mes (1-31)."
            )

        created = await self._service.create_recurring(rec, user_id)
        logger.info("Tool created recurring", recurring_id=created.id, user_id=user_id)
        kind = "ingreso" if created.transaction_type == TransactionType.INCOME else "gasto"
        method = f", {created.payment_method.value}" if created.payment_method else ""
        return (
            f"✅ Recurrente creado: {created.description} — ${created.amount} ({kind}, "
            f"cada día {created.day_of_month}{method}). Próximo: {created.next_run_date}."
        )

    async def _list(self, user_id: UserId) -> str:
        items = await self._service.list_recurring(user_id)
        if not items:
            return "No tienes movimientos recurrentes configurados."
        lines = [
            f"- {r.description}: ${r.amount} (cada día {r.day_of_month}, "
            f"próximo {r.next_run_date}, {'activo' if r.active else 'pausado'})"
            for r in items
        ]
        return f"{len(items)} recurrente(s):\n" + "\n".join(lines)

    async def _update(self, args: dict[str, Any], user_id: UserId) -> str:
        rec, clarification = await self._resolve(args, user_id)
        if clarification is not None:
            return clarification
        if rec is None:
            return _not_found(args)

        payment_method = _to_payment_method(args.get("payment_method"))
        unlink_card = bool(args.get("unlink_card"))
        # Credit (or a named card) must resolve to a real card — ask which one if
        # it's ambiguous, mirroring create — so we never link a card we can't find.
        card_id: str | None = None
        card_name = str(args.get("card_name", "")).strip()
        if card_name or payment_method == PaymentMethod.CREDITO:
            card, card_clarification = await self._resolve_card(
                args, payment_method, user_id
            )
            if card_clarification is not None:
                return card_clarification
            if card is not None:
                card_id = card.id
                payment_method = PaymentMethod.CREDITO

        try:
            update = RecurringUpdate(
                amount=_opt_decimal(args.get("new_amount")),
                description=_opt_str(args.get("new_description")),
                transaction_type=_to_type(args.get("new_type")),
                category=_to_category(args.get("new_category")),
                payment_method=payment_method,
                card_id=card_id,
                clear_card=unlink_card,
                day_of_month=_opt_int(args.get("new_day_of_month")),
            )
        except ValidationError as e:
            logger.warning("Invalid recurring update args from tool", error=str(e))
            return "No pude actualizar el recurrente: revisa el monto y el día (1-31)."

        if not update.model_dump(exclude_defaults=True):
            return (
                "¿Qué quieres cambiar del recurrente? (nombre, monto, tipo, día, "
                "categoría, método o tarjeta)"
            )

        updated = await self._service.update_recurring(rec.id, user_id, update)
        return (
            f"✏️ Actualicé el recurrente '{updated.description}' — ${updated.amount} "
            f"(cada día {updated.day_of_month}, próximo {updated.next_run_date})."
        )

    async def _delete(self, args: dict[str, Any], user_id: UserId) -> str:
        rec, clarification = await self._resolve(args, user_id)
        if clarification is not None:
            return clarification
        if rec is None:
            return _not_found(args)
        await self._service.delete_recurring(rec.id, user_id)
        logger.info("Tool deleted recurring", recurring_id=rec.id, user_id=user_id)
        return f"🗑️ Eliminé el recurrente '{rec.description}'."

    async def _set_active(
        self, args: dict[str, Any], user_id: UserId, *, active: bool
    ) -> str:
        rec, clarification = await self._resolve(args, user_id)
        if clarification is not None:
            return clarification
        if rec is None:
            return _not_found(args)
        updated = await self._service.set_active(rec.id, user_id, active)
        if active:
            return (
                f"▶️ Reanudé el recurrente '{updated.description}'. "
                f"Próximo registro: {updated.next_run_date}."
            )
        return f"⏸️ Pausé el recurrente '{updated.description}'. No se registrará hasta reanudarlo."

    async def _resolve(
        self, args: dict[str, Any], user_id: UserId
    ) -> tuple[RecurringTransaction | None, str | None]:
        """Find the template the user means by its description.

        Returns ``(template, clarification)``. When more than one template matches
        (e.g. 'Netflix' and 'Netflix Premium'), returns a disambiguation question
        and no template — a destructive op must never silently pick the first.
        """
        description = str(args.get("description", "")).strip()
        if not description:
            return None, None
        matches = await self._service.find_matches(description, user_id)
        if not matches:
            return None, None
        if len(matches) > 1:
            return None, _which_recurring_message(description, matches)
        return matches[0], None

    async def _resolve_card(
        self, args: dict[str, Any], payment_method: PaymentMethod | None, user_id: UserId
    ) -> tuple[CreditCard | None, str | None]:
        """Resolve the credit card a recurrente belongs to.

        Returns ``(card, clarification)``. By name if the user gave one; otherwise,
        for a credit recurrente with exactly one card, use it automatically. When
        the recurrente is on credit and the card is ambiguous (several cards and no
        name, or a name we can't find), returns a clarification question and no
        card, so a credit recurrente is never left unlinked.
        """
        card_name = str(args.get("card_name", "")).strip()
        if not card_name and payment_method != PaymentMethod.CREDITO:
            return None, None
        if self._cards is None:
            return None, None
        cards = await self._cards.list_cards(user_id)
        if not cards:
            return None, None  # No cards on file: nothing to link or ask about.
        if card_name:
            card = await self._cards.resolve_by_name(card_name, user_id)
            if card is not None:
                return card, None
            return None, _which_card_message(cards, unknown=card_name)
        if len(cards) == 1:
            return cards[0], None
        return None, _which_card_message(cards)


def _not_found(args: dict[str, Any]) -> str:
    name = str(args.get("description", "")).strip()
    return f"No encontré un recurrente llamado '{name}'. ¿Puedes indicar el nombre exacto?"


def _which_recurring_message(
    query: str, matches: list[RecurringTransaction]
) -> str:
    """Ask which template the user means when several match the description."""
    names = ", ".join(f"'{r.description}'" for r in matches)
    return (
        f"Tengo varios recurrentes que coinciden con '{query}': {names}. "
        "¿Cuál de ellos?"
    )


def _which_card_message(cards: list[CreditCard], unknown: str = "") -> str:
    """Ask which credit card a recurrente belongs to, listing the user's cards."""
    names = ", ".join(card.name for card in cards)
    prefix = f"No encontré una tarjeta llamada «{unknown}». " if unknown else ""
    return (
        f"{prefix}¿A cuál de tus tarjetas asocio este recurrente? "
        f"Tienes: {names}. Dime el nombre y lo creo."
    )


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"Invalid amount: {value!r}") from e


def _opt_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid integer: {value!r}") from e


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opt_str(value: Any) -> str | None:
    if not value:
        return None
    return str(value).strip() or None


def _to_type(value: Any) -> TransactionType | None:
    if not value:
        return None
    try:
        return TransactionType(str(value).lower())
    except ValueError:
        return None


def _to_category(value: Any) -> str | None:
    if not value:
        return None
    return normalize_category(str(value))


def _to_payment_method(value: Any) -> PaymentMethod | None:
    if not value:
        return None
    try:
        return PaymentMethod(str(value).lower())
    except ValueError:
        return None


def _to_frequency(value: Any) -> RecurringFrequency:
    if not value:
        return RecurringFrequency.MONTHLY
    try:
        return RecurringFrequency(str(value).lower())
    except ValueError:
        return RecurringFrequency.MONTHLY
