"""Transaction tools for conversational data operations.

Thin wrappers over ``TransactionService`` exposed to the LLM as callable tools.

Security: ``user_id`` is supplied by the toolkit from the authenticated context
at dispatch time and is NEVER part of the tool schema nor read from the model's
arguments. The model only provides the transaction data.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.agents.nodes.analyst_constants import get_category_label
from app.agents.nodes.analyst_utils import (
    aggregate_by_category,
    calculate_totals,
    detect_patterns,
)
from app.core.exceptions import TransactionNotFoundError
from app.core.logging import get_logger
from app.shared.types import PaymentMethod, TransactionType, UserId, normalize_category
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import CreditCard
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import Transaction, TransactionCreate

logger = get_logger(__name__)

REGISTER_TRANSACTION_TOOL = "register_transaction"
QUERY_TRANSACTIONS_TOOL = "query_transactions"
ANALYZE_SPENDING_TOOL = "analyze_spending"
UPDATE_TRANSACTION_TOOL = "update_transaction"
DELETE_TRANSACTION_TOOL = "delete_transaction"

# Transactions fetched (one page) to aggregate; ample for personal-finance volumes.
ANALYZE_FETCH_LIMIT = 500

# Tool schemas in OpenAI function-calling format, consumed by
# LLMInterface.generate_with_tools. Note: no `user_id` parameter is exposed.
TRANSACTION_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": REGISTER_TRANSACTION_TOOL,
            "description": (
                "Registra una transacción (ingreso o gasto) del usuario. Úsala cuando "
                "el usuario menciona que gastó, pagó, compró o recibió dinero."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number", "description": "Monto, mayor a 0"},
                    "description": {
                        "type": "string",
                        "description": "Descripción del movimiento",
                    },
                    "transaction_type": {
                        "type": "string",
                        "enum": ["income", "expense"],
                        "description": "Tipo: ingreso (income) o gasto (expense)",
                    },
                    "transaction_date": {
                        "type": "string",
                        "description": "Fecha ISO YYYY-MM-DD; si no se indica, se usa hoy",
                    },
                    "category": {
                        "type": "string",
                        "description": (
                            "Categoría del gasto: pásala SIEMPRE. Si el usuario la nombra, "
                            "úsala tal cual. Si no, dedúcela de la descripción: usa una "
                            "categoría conocida si encaja, o una PROPIA corta y con sentido "
                            "si es algo distinto (p. ej. 'envíos', 'donaciones'). No fuerces "
                            "una categoría conocida que no corresponde."
                        ),
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["efectivo", "credito"],
                        "description": (
                            "Método de pago SOLO si el usuario lo menciona para ESTE gasto: "
                            "'credito' para tarjeta de crédito; 'efectivo' para efectivo, "
                            "débito o transferencia. Omítelo si no lo dice en este gasto. "
                            "NUNCA lo asumas de un gasto anterior ni de la conversación."
                        ),
                    },
                    "card_name": {
                        "type": "string",
                        "description": (
                            "Nombre de la tarjeta de crédito SOLO si el usuario la nombra "
                            "para ESTE gasto. Pásalo EXACTAMENTE como lo escribió (si dijo "
                            "'rappid', pasa 'rappid'); no lo corrijas ni lo cambies por una "
                            "marca (no 'RappiCard'). Se busca por coincidencia parcial. "
                            "NUNCA la infieras de un gasto anterior: si no dijo cuál, omítela "
                            "y el sistema preguntará."
                        ),
                    },
                },
                "required": ["amount", "description", "transaction_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": QUERY_TRANSACTIONS_TOOL,
            "description": (
                "Consulta las transacciones del usuario, opcionalmente filtrando por "
                "tipo y categoría."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_type": {"type": "string", "enum": ["income", "expense"]},
                    "category": {"type": "string"},
                    "page": {"type": "integer", "minimum": 1},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": ANALYZE_SPENDING_TOOL,
            "description": (
                "Analiza los gastos del usuario en un periodo: totales (ingresos, "
                "gastos, balance), desglose por categoría y patrones. Úsala para "
                "'¿en qué gasto más?', resúmenes, análisis o antes de dar "
                "recomendaciones de ahorro."
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
            "name": UPDATE_TRANSACTION_TOOL,
            "description": (
                "Corrige una transacción existente. La identificas por su DESCRIPCIÓN "
                "(y opcionalmente monto/fecha si hay varias parecidas); el sistema la "
                "encuentra — tú NO manejas ids. Úsala SOLO tras confirmar el cambio con "
                "el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Descripción de la transacción a corregir (ej. 'YouTube')",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Monto actual, para desambiguar si hay varias iguales",
                    },
                    "transaction_date": {
                        "type": "string",
                        "description": "Fecha actual YYYY-MM-DD, para desambiguar (opcional)",
                    },
                    "new_amount": {"type": "number", "description": "Nuevo monto (opcional)"},
                    "new_description": {"type": "string", "description": "Nueva descripción (opcional)"},
                    "new_category": {"type": "string", "description": "Nueva categoría (opcional)"},
                    "new_transaction_date": {
                        "type": "string",
                        "description": "Nueva fecha YYYY-MM-DD (opcional)",
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["efectivo", "credito"],
                        "description": "Nuevo método de pago (opcional)",
                    },
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": DELETE_TRANSACTION_TOOL,
            "description": (
                "Elimina una transacción existente. La identificas por su DESCRIPCIÓN "
                "(y opcionalmente monto/fecha si hay varias parecidas); el sistema la "
                "encuentra — tú NO manejas ids. Úsala SOLO tras confirmar con el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Descripción del gasto a eliminar (ej. 'YouTube')",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Monto, para desambiguar si hay varios (opcional)",
                    },
                    "transaction_date": {
                        "type": "string",
                        "description": "Fecha YYYY-MM-DD, para desambiguar (opcional)",
                    },
                },
                "required": ["description"],
            },
        },
    },
]


class TransactionToolkit:
    """Exposes transaction tools to the LLM and dispatches its tool calls.

    The toolkit wraps the application ``TransactionService``; it contains no
    business logic itself.
    """

    def __init__(
        self,
        service: TransactionServiceABC,
        cards: "CreditCardServiceABC | None" = None,
    ) -> None:
        self._service = service
        # Optional: resolves a credit charge to a specific card by name.
        self._cards = cards

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """Tool schemas to pass to ``generate_with_tools``."""
        return TRANSACTION_TOOL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        """Execute a tool call by name, binding ``user_id`` from the auth context.

        Args:
            name: Tool name returned by the LLM.
            arguments: Arguments produced by the LLM (``user_id`` is ignored).
            user_id: Authenticated user id (never taken from the model).

        Returns:
            A human-readable result string to feed back to the LLM.

        Raises:
            ValueError: If the tool name is unknown.
        """
        if name == REGISTER_TRANSACTION_TOOL:
            return await self._register(arguments, user_id)
        if name == QUERY_TRANSACTIONS_TOOL:
            return await self._query(arguments, user_id)
        if name == ANALYZE_SPENDING_TOOL:
            return await self._analyze(arguments, user_id)
        if name == UPDATE_TRANSACTION_TOOL:
            return await self._update(arguments, user_id)
        if name == DELETE_TRANSACTION_TOOL:
            return await self._delete(arguments, user_id)
        raise ValueError(f"Unknown transaction tool: {name}")

    async def _register(self, args: dict[str, Any], user_id: UserId) -> str:
        payment_method = _to_payment_method(args.get("payment_method"))
        card_id, clarification = await self._resolve_card_id(args, payment_method, user_id)
        # Credit charge with an ambiguous card: ask which one instead of registering
        # it unlinked. Deterministic, so it never depends on the prompt remembering.
        if clarification is not None:
            return clarification
        try:
            transaction = TransactionCreate(
                amount=_to_decimal(args.get("amount")),
                description=str(args.get("description", "")).strip(),
                transaction_type=TransactionType(args.get("transaction_type", "expense")),
                transaction_date=_to_date(args.get("transaction_date")),
                category=_to_category(args.get("category")),
                payment_method=payment_method,
                card_id=card_id,
            )
        except (ValidationError, ValueError) as e:
            logger.warning("Invalid transaction args from tool", error=str(e))
            return (
                "No pude registrar la transacción: los datos no son válidos "
                "(revisa el monto, que debe ser mayor a 0, y el tipo)."
            )

        created = await self._service.create_transaction(transaction, user_id)
        logger.info("Tool registered transaction", transaction_id=created.id, user_id=user_id)
        method = f", {created.payment_method.value}" if created.payment_method else ""
        return (
            f"✅ Registré: {created.description} — ${created.amount} "
            f"({created.category}, {created.transaction_date}{method})."
        )

    async def _resolve_card_id(
        self, args: dict[str, Any], payment_method: PaymentMethod | None, user_id: UserId
    ) -> tuple[str | None, str | None]:
        """Resolve the credit card a charge belongs to.

        Returns ``(card_id, clarification)``. By name if the user said one;
        otherwise, if the user has exactly one card, use it automatically. When
        the charge is on credit and the card is ambiguous (several cards and no
        name, or a name we can't find), returns a clarification question and no
        id, so the caller asks which card instead of leaving the charge unlinked.
        """
        if payment_method != PaymentMethod.CREDITO or self._cards is None:
            return None, None
        cards = await self._cards.list_cards(user_id)
        if not cards:
            return None, None  # No cards on file: nothing to link or ask about.
        card_name = str(args.get("card_name", "")).strip()
        if card_name:
            card = await self._cards.resolve_by_name(card_name, user_id)
            if card is not None:
                return card.id, None
            return None, _which_card_message(cards, unknown=card_name)
        if len(cards) == 1:
            return cards[0].id, None
        return None, _which_card_message(cards)

    async def _query(self, args: dict[str, Any], user_id: UserId) -> str:
        items, total = await self._service.list_transactions(
            user_id,
            page=_to_int(args.get("page"), default=1, minimum=1),
            page_size=_to_int(args.get("page_size"), default=20, minimum=1, maximum=100),
            transaction_type=_to_type(args.get("transaction_type")),
            category=_to_category(args.get("category")),
        )
        if not items:
            return "No se encontraron transacciones con esos filtros."

        # No ids: update/delete resolve the transaction by description/amount, so
        # the agent never has to copy a UUID (LLMs mangle them).
        lines = [
            f"- {t.description}: ${t.amount} ({t.category}, {t.transaction_date}"
            + (f", {t.payment_method.value}" if t.payment_method else "")
            + ")"
            for t in items[:10]
        ]
        return f"{total} transacción(es) encontradas:\n" + "\n".join(lines)

    async def _analyze(self, args: dict[str, Any], user_id: UserId) -> str:
        period = str(args.get("period", "este_mes")).lower()
        items, _ = await self._service.list_transactions(
            user_id, page=1, page_size=ANALYZE_FETCH_LIMIT
        )
        start, end = _period_range(period)
        transactions = [
            _tx_to_dict(t) for t in items if _in_period(t.transaction_date, start, end)
        ]
        if not transactions:
            return f"No hay transacciones registradas en el periodo ({_period_label(period)})."

        income, expenses = calculate_totals(transactions)
        by_category = aggregate_by_category(transactions)
        patterns = detect_patterns(transactions, by_category, expenses)
        return _format_analysis(period, income, expenses, by_category, patterns)

    async def _update(self, args: dict[str, Any], user_id: UserId) -> str:
        target = await self._resolve_transaction(args, user_id)
        if target is None:
            return "No encontré esa transacción. ¿Puedes darme más detalles (monto o fecha)?"
        try:
            updated = await self._service.update_transaction(
                target.id,
                user_id,
                amount=_opt_decimal(args.get("new_amount")),
                description=_opt_str(args.get("new_description")),
                category=_to_category(args.get("new_category")),
                transaction_date=_opt_date(args.get("new_transaction_date")),
                payment_method=_to_payment_method(args.get("payment_method")),
            )
        except TransactionNotFoundError:
            return "No encontré esa transacción para actualizar."
        method = f", {updated.payment_method.value}" if updated.payment_method else ""
        return (
            f"✏️ Actualicé: {updated.description} — ${updated.amount} "
            f"({updated.category}, {updated.transaction_date}{method})."
        )

    async def _delete(self, args: dict[str, Any], user_id: UserId) -> str:
        target = await self._resolve_transaction(args, user_id)
        if target is None:
            return "No encontré esa transacción (quizás ya no existe)."
        try:
            deleted = await self._service.delete_transaction(target.id, user_id)
        except TransactionNotFoundError:
            return "No encontré esa transacción (quizás ya no existe)."
        return f"🗑️ Eliminé: {deleted.description} — ${deleted.amount} ({deleted.transaction_date})."

    async def _resolve_transaction(
        self, args: dict[str, Any], user_id: UserId
    ) -> Transaction | None:
        """Find the transaction the user means by description (+ optional amount/date).

        The LLM never handles ids — it describes the transaction and we resolve it
        here. Among duplicates, the most recent match is returned (fine for a
        "cualquiera" delete).
        """
        description = str(args.get("description", "")).lower().strip()
        if not description:
            return None
        amount = _opt_decimal(args.get("amount"))
        tx_date = _opt_date(args.get("transaction_date"))

        items, _ = await self._service.list_transactions(user_id, page=1, page_size=100)
        matches = [
            t
            for t in items
            if description in t.description.lower()
            and (amount is None or t.amount == amount)
            and (tx_date is None or t.transaction_date == tx_date)
        ]
        return matches[0] if matches else None


def _tx_to_dict(t: Transaction) -> dict[str, Any]:
    """Shape a transaction for the analyst_utils aggregation helpers."""
    return {
        "amount": float(t.amount),
        "transaction_type": t.transaction_type.value,
        "category": t.category,
        "transaction_date": t.transaction_date,
        "description": t.description,
    }


def _period_range(period: str) -> tuple[date | None, date | None]:
    """Return (start, end) dates for a named period; (None, None) means all-time."""
    today = datetime.now(UTC).date()
    if period == "todo":
        return None, None
    if period == "mes_pasado":
        last_month_end = today.replace(day=1) - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    # Default: current month to date.
    return today.replace(day=1), today


def _in_period(day: date, start: date | None, end: date | None) -> bool:
    if start is None or end is None:
        return True
    return start <= day <= end


def _period_label(period: str) -> str:
    return {"todo": "todo el historial", "mes_pasado": "mes pasado"}.get(period, "este mes")


def _format_analysis(
    period: str,
    income: float,
    expenses: float,
    by_category: dict[str, float],
    patterns: list[str],
) -> str:
    """Format the spending analysis for the LLM to phrase back to the user."""
    lines = [
        f"Resumen de gastos ({_period_label(period)}):",
        f"- Ingresos: ${income:,.2f}",
        f"- Gastos: ${expenses:,.2f}",
        f"- Balance: ${income - expenses:,.2f}",
        "",
        "Gasto por categoría (mayor a menor):",
    ]
    if by_category:
        for category, amount in by_category.items():
            pct = (amount / expenses * 100) if expenses > 0 else 0
            lines.append(f"- {get_category_label(category)}: ${amount:,.2f} ({pct:.0f}%)")
    else:
        lines.append("- Sin gastos en el periodo")
    if patterns:
        lines.append("")
        lines.append("Patrones detectados:")
        lines.extend(f"- {pattern}" for pattern in patterns)
    return "\n".join(lines)


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise ValueError(f"Invalid amount: {value!r}") from e


def _opt_decimal(value: Any) -> Decimal | None:
    """Parse an optional amount for updates; None means 'leave unchanged'."""
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


def _opt_date(value: Any) -> date | None:
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _to_date(value: Any) -> date:
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return datetime.now(UTC).date()
    return datetime.now(UTC).date()


def _to_category(value: Any) -> str | None:
    # Known or custom: normalize and pass through. Empty -> None so the service
    # auto-categorizes from the description.
    if not value:
        return None
    return normalize_category(str(value))


def _which_card_message(cards: list[CreditCard], unknown: str = "") -> str:
    """Ask which credit card a charge belongs to, listing the user's cards."""
    names = ", ".join(card.name for card in cards)
    prefix = f"No encontré una tarjeta llamada «{unknown}». " if unknown else ""
    return (
        f"{prefix}¿A cuál de tus tarjetas cargo este gasto? "
        f"Tienes: {names}. Dime el nombre y lo registro."
    )


def _to_type(value: Any) -> TransactionType | None:
    if not value:
        return None
    try:
        return TransactionType(str(value).lower())
    except ValueError:
        return None


def _to_payment_method(value: Any) -> PaymentMethod | None:
    if not value:
        return None
    try:
        return PaymentMethod(str(value).lower())
    except ValueError:
        return None  # Unknown -> leave it unset rather than guessing.


def _to_int(value: Any, *, default: int, minimum: int, maximum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if result < minimum:
        return minimum
    if maximum is not None and result > maximum:
        return maximum
    return result
