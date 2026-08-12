"""Transaction tools for conversational data operations.

Thin wrappers over ``TransactionService`` exposed to the LLM as callable tools.

Security: ``user_id`` is supplied by the toolkit from the authenticated context
at dispatch time and is NEVER part of the tool schema nor read from the model's
arguments. The model only provides the transaction data.
"""

import asyncio
import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Final

from pydantic import ValidationError

from app.agents.nodes.analyst_constants import TOP_EXPENSES_LIMIT, get_category_label
from app.agents.nodes.analyst_utils import (
    aggregate_by_category,
    calculate_totals,
    detect_patterns,
    top_expenses,
)
from app.core.exceptions import TransactionNotFoundError
from app.core.logging import get_logger
from app.shared.clock import current_today
from app.shared.periods import period_label, resolve_period
from app.shared.types import (
    PaymentMethod,
    TransactionId,
    TransactionType,
    UserId,
    normalize_category,
)
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.cards.cycle import compute_cycle, next_payment_date
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import CreditCard
from app.src.transactions.constants import DELETE_CONCURRENCY, MAX_INSTALLMENTS
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import Transaction, TransactionCreate

logger = get_logger(__name__)

REGISTER_TRANSACTION_TOOL = "register_transaction"
QUERY_TRANSACTIONS_TOOL = "query_transactions"
ANALYZE_SPENDING_TOOL = "analyze_spending"
UPDATE_TRANSACTION_TOOL = "update_transaction"
DELETE_TRANSACTION_TOOL = "delete_transaction"
# Named 'delete_by_filter' (not 'delete_movements') to avoid colliding with
# manage_category's boolean 'delete_movements' param, which confuses tool routing.
DELETE_BY_FILTER_TOOL = "delete_by_filter"

# Transactions fetched (one page) to aggregate; ample for personal-finance volumes.
ANALYZE_FETCH_LIMIT = 500

# Asked (deterministically) when an expense has no payment method AND the user has
# cards, so we never pre-register a pm-less row that a "con tarjeta" follow-up would
# duplicate. Users with no cards skip this: the charge can only be cash.
ASK_PAYMENT_METHOD_MESSAGE: Final[str] = (
    "¿Este gasto lo pagaste en efectivo o con tarjeta de crédito?"
)

# Cap on how many query results to list back (the count and total still cover all).
QUERY_DISPLAY_LIMIT = 25

# Accepted `period` args: named periods or a strict YYYY-MM month. Anything else is
# rejected instead of silently falling back to the current month (resolve_period).
_NAMED_PERIODS: Final[frozenset[str]] = frozenset({"este_mes", "mes_pasado", "todo"})
_MONTH_ARG_RE: Final = re.compile(r"^\d{4}-\d{2}$")


def _norm(text: str) -> str:
    """Lowercase and strip accents so 'Buñuelos'/'bunuelos' compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _matches_term(transaction: Transaction, term: str) -> bool:
    """True if ``term`` matches the transaction's description OR category.

    Accent-insensitive and matches in either direction, so the agent can pass a
    longer label than what's stored ("Envío a Venezuela" vs "Venezuela"), the
    category instead of the description ("venezuela" for a row described "MERCA
    FACIL"), or a differently-accented spelling ("bunuelos" vs "buñuelos").
    """
    needle = _norm(term)
    if not needle:
        return False
    fields = [_norm(transaction.description), _norm(transaction.category or "")]
    # Reverse match (stored field inside a longer term) is gated on length so a
    # 2-3 char category ("gym") can't swallow a verbose phrase the agent passes.
    return any(f and (needle in f or (len(f) >= 4 and f in needle)) for f in fields)

# Installment rows are stored as separate transactions named "<purchase> (cuota i/n)".
# This matches that suffix so a deferred purchase can be treated as one group.
_CUOTA_RE: Final = re.compile(r"\s*\(cuota\s+\d+/(\d+)\)\s*$", re.IGNORECASE)


def _cuota_base(description: str) -> str:
    """The purchase name without its '(cuota i/n)' suffix."""
    return _CUOTA_RE.sub("", description).strip()


def _cuota_count(description: str) -> int | None:
    """Total number of installments if this row is one of a split, else ``None``."""
    match = _CUOTA_RE.search(description)
    return int(match.group(1)) if match else None


def _installment_groups(rows: list[Transaction]) -> list[list[Transaction]]:
    """Cluster rows into installment groups (same purchase name + count).

    Non-installment rows become singletons. All the '(cuota i/n)' rows of a
    purchase — including accidental duplicate registrations — fall in one group,
    so deleting the purchase removes every part rather than a single cuota.
    (A genuine repeat of the same item on the same plan also merges; acceptable
    for the dedup use case this serves.)
    """
    groups: dict[object, list[Transaction]] = {}
    for row in rows:
        count = _cuota_count(row.description)
        key: object = (_cuota_base(row.description).lower(), count) if count else row.id
        groups.setdefault(key, []).append(row)
    return list(groups.values())


def _pick_group(
    groups: list[list[Transaction]], amount: Decimal | None
) -> list[Transaction] | None:
    """Choose the group the user means.

    With an amount, match a single row, the installment total, or a per-cuota
    value (in that order) — so both "delete X for <total>" and "delete X for
    <cuota>" work. With no amount, fall back to the most recent group.
    """
    if not groups:
        return None
    if amount is None:
        return max(groups, key=lambda g: max(t.transaction_date for t in g))
    for group in groups:
        if len(group) == 1 and group[0].amount == amount:
            return group
    for group in groups:
        if len(group) > 1 and sum((t.amount for t in group), Decimal("0")) == amount:
            return group
    for group in groups:
        if any(t.amount == amount for t in group):
            return group
    return None


def _resolve_delete_group(
    pool: list[Transaction],
    description: str,
    amount: Decimal | None,
    tx_date: date | None,
) -> list[Transaction] | None:
    """Resolve the transaction (or full installment group) a descriptor refers to."""
    matched = [t for t in pool if _matches_term(t, description)]
    # A date narrows to a single row ONLY when the match isn't an installment
    # purchase — otherwise it would split the group and leave orphan cuotas.
    if tx_date is not None and not any(_cuota_count(t.description) for t in matched):
        matched = [t for t in matched if t.transaction_date == tx_date]
    return _pick_group(_installment_groups(matched), amount)

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
                    "cuotas": {
                        "type": "integer",
                        "minimum": 1,
                        "description": (
                            "Número de cuotas si la compra fue DIFERIDA a plazos (p. ej. 'a 4 "
                            "cuotas'). En ese caso 'amount' es el TOTAL de la compra y el "
                            "sistema lo reparte en N gastos mensuales. Omítelo o 1 si fue pago "
                            "único. Una compra a cuotas es con tarjeta de crédito."
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
                "Consulta las transacciones del usuario, filtrando por tipo, categoría, "
                "tarjeta, MES y/o método de pago. Devuelve TODAS las que cumplen y su "
                "total (p. ej. 'transporte en efectivo en junio', 'movimientos de mi "
                "tarjeta Nu'). Úsala siempre que pregunten por movimientos de un mes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_type": {"type": "string", "enum": ["income", "expense"]},
                    "category": {"type": "string"},
                    "card_name": {
                        "type": "string",
                        "description": "Filtrar por la tarjeta cuyo nombre diga el usuario",
                    },
                    "period": {
                        "type": "string",
                        "description": (
                            "Mes a consultar: 'este_mes', 'mes_pasado', 'todo' o "
                            "'YYYY-MM' (p. ej. '2026-06' para junio de 2026)."
                        ),
                    },
                    "payment_method": {
                        "type": "string",
                        "enum": ["efectivo", "credito"],
                        "description": "Filtrar por método de pago (efectivo o crédito)",
                    },
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
                "Elimina gastos ESPECÍFICOS: uno, o VARIOS pasándolos en 'items'. "
                "Cada uno se identifica por su DESCRIPCIÓN (+ monto/fecha si hay "
                "parecidos); el sistema los encuentra, tú NO manejas ids. Para borrar "
                "por criterio (una tarjeta, una categoría o un rango de fechas) usa "
                "delete_by_filter. Úsala SOLO tras confirmar con el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Descripción del gasto a eliminar (para UNO solo)",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Monto, para desambiguar si hay varios (opcional)",
                    },
                    "transaction_date": {
                        "type": "string",
                        "description": "Fecha YYYY-MM-DD, para desambiguar (opcional)",
                    },
                    "items": {
                        "type": "array",
                        "description": (
                            "Para borrar VARIOS de una vez: lista de gastos, cada uno "
                            "{description, amount?, transaction_date?}."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "amount": {"type": "number"},
                                "transaction_date": {"type": "string"},
                            },
                            "required": ["description"],
                        },
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": DELETE_BY_FILTER_TOOL,
            "description": (
                "Borra EN BLOQUE por CRITERIO: tarjeta, categoría/rubro y/o tiempo "
                "(p. ej. 'borra todo transporte de julio', 'borra los de Nu de agosto', "
                "'borra del 5 al 20 de julio'). SIEMPRE requiere un alcance temporal "
                "(period o start_date+end_date); tarjeta y categoría son filtros extra. "
                "Destructivo: confírmalo ('¿Borro los N …?') y úsala SOLO tras el 'sí'. "
                "Para borrar gastos puntuales/una lista usa delete_transaction."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "card_name": {
                        "type": "string",
                        "description": "Filtrar por tarjeta (opcional, ej. 'Nu')",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filtrar por categoría/rubro (opcional, ej. 'transporte')",
                    },
                    "period": {
                        "type": "string",
                        "description": "Alcance: 'este_mes', 'mes_pasado', 'todo' o 'YYYY-MM'",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Inicio del rango YYYY-MM-DD (junto con end_date)",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Fin del rango YYYY-MM-DD (junto con start_date)",
                    },
                },
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
        budgets: "BudgetServiceABC | None" = None,
    ) -> None:
        self._service = service
        # Optional: resolves a credit charge to a specific card by name.
        self._cards = cards
        # Optional: lets a registered expense warn when it crosses its budget.
        self._budgets = budgets

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
        if name == DELETE_BY_FILTER_TOOL:
            return await self._delete_movements(arguments, user_id)
        if name == DELETE_TRANSACTION_TOOL:
            return await self._delete(arguments, user_id)
        raise ValueError(f"Unknown transaction tool: {name}")

    async def _register(self, args: dict[str, Any], user_id: UserId) -> str:
        payment_method = _to_payment_method(args.get("payment_method"))
        card, clarification = await self._resolve_card_id(args, payment_method, user_id)
        # Credit charge with an ambiguous card: ask which one instead of registering
        # it unlinked. Deterministic, so it never depends on the prompt remembering.
        if clarification is not None:
            return clarification
        # A charge linked to a card is on credit by definition — set it so the
        # movement shows its card and hits the right (payment-month) budget.
        if card is not None:
            payment_method = PaymentMethod.CREDITO

        # Expense with no stated method and no card: don't guess. If the user has NO
        # cards it can only be cash → efectivo (don't ask). If they DO have cards, ask
        # instead of registering — otherwise a pm-less row is created now and a
        # follow-up "con tarjeta" registers a SECOND one (the duplicate we saw).
        # Installments are credit by definition, so they skip this.
        requested_cuotas = _to_int(args.get("cuotas"), default=1, minimum=1)
        is_expense = args.get("transaction_type", "expense") == "expense"
        no_card_named = not str(args.get("card_name", "")).strip()
        if (
            is_expense
            and payment_method is None
            and card is None
            and no_card_named
            and requested_cuotas <= 1
        ):
            if self._cards is not None and await self._cards.list_cards(user_id):
                return ASK_PAYMENT_METHOD_MESSAGE
            payment_method = PaymentMethod.EFECTIVO

        # Reuse an existing category on a close match (typo tolerance), so a
        # variant like "improvistos" folds into the user's "imprevistos" instead
        # of fragmenting. Skipped when no category is given (service auto-tags).
        category = _to_category(args.get("category"))
        if category is not None:
            category = await self._service.resolve_category(category, user_id)
        transaction_date = _to_date(args.get("transaction_date"))
        # A credit charge hits the budget the month its statement is paid, not the
        # purchase month; cash/debit hit the purchase month.
        budget_date = _credit_budget_date(card, transaction_date)
        try:
            transaction = TransactionCreate(
                amount=_to_decimal(args.get("amount")),
                description=str(args.get("description", "")).strip(),
                transaction_type=TransactionType(args.get("transaction_type", "expense")),
                transaction_date=transaction_date,
                budget_date=budget_date,
                category=category,
                payment_method=payment_method,
                card_id=card.id if card else None,
            )
        except (ValidationError, ValueError) as e:
            logger.warning("Invalid transaction args from tool", error=str(e))
            return (
                "No pude registrar la transacción: los datos no son válidos "
                "(revisa el monto, que debe ser mayor a 0, y el tipo)."
            )

        # Deferred purchase: the service spreads the total across N monthly installments.
        installments = min(requested_cuotas, MAX_INSTALLMENTS)
        if installments > 1:
            parts = await self._service.create_installments(transaction, installments, user_id)
            first = parts[0]
            logger.info("Tool registered installments", installments=installments, user_id=user_id)
            # Be explicit when we capped the request, so the reply never claims a
            # different number than what the user asked for.
            capped = (
                f" (pediste {requested_cuotas}; el máximo es {MAX_INSTALLMENTS})"
                if requested_cuotas > MAX_INSTALLMENTS
                else ""
            )
            return (
                f"✅ Registré tu compra de ${transaction.amount} en {installments} cuotas de "
                f"${first.amount} ({first.category}), desde {transaction.transaction_date} "
                f"y una cada mes.{capped}"
            )

        created = await self._service.create_transaction(transaction, user_id)
        logger.info("Tool registered transaction", transaction_id=created.id, user_id=user_id)
        method = f", {created.payment_method.value}" if created.payment_method else ""
        # Tell the user when a credit charge lands on a DIFFERENT month's budget
        # (compare by month, not exact day, to avoid noise within the same month).
        impact = ""
        if created.budget_date.strftime("%Y-%m") != created.transaction_date.strftime("%Y-%m"):
            impact = f" Afectará tu presupuesto de {_budget_month_label(created.budget_date)}."
        confirmation = (
            f"✅ Registré: {created.description} — ${created.amount} "
            f"({created.category}, {created.transaction_date}{method}).{impact}"
        )
        return f"{confirmation}{await self._budget_nudge(created, user_id)}"

    async def _budget_nudge(self, created: Transaction, user_id: UserId) -> str:
        """Best-effort in-chat budget alert appended to an expense confirmation.

        Returns a short warning (already prefixed with ``\\n``) only when THIS
        expense is the one that crosses its category budget's alert threshold or
        its 100% limit — so later expenses in an already-over budget don't repeat
        the nudge. Best-effort: it must NEVER break or fail a registration, so any
        lookup error is swallowed and yields no nudge.
        """
        if (
            self._budgets is None
            or created.transaction_type != TransactionType.EXPENSE
            or created.category is None
        ):
            return ""
        try:
            budget = await self._budgets.resolve_budget(created.category, user_id)
            if budget is None:
                return ""
            # resolve_budget can match by NAME to a differently-categorized budget,
            # whose `spent` wouldn't include this expense — making the `before`
            # baseline wrong. Only nudge when the budget actually covers this
            # category (or is an overall budget, category=None → sums everything).
            if budget.category is not None and budget.category != created.category:
                return ""
            status = await self._budgets.get_budget_status(
                budget.id, user_id, as_of=current_today()
            )
            if not status.budget.alert_enabled:
                return ""
            # A credit charge for a future month doesn't touch the current period.
            if not (status.period_start <= created.budget_date <= status.period_end):
                return ""
            limit = status.budget.amount
            if limit <= 0:
                return ""
            spent_after = status.spent
            before = spent_after - created.amount
            threshold_amt = limit * status.budget.alert_threshold / 100
            name = status.budget.name or created.category
            # Nudge only on the crossing tx (over-budget takes priority over the
            # approaching-threshold warning when a single tx trips both).
            if before < limit <= spent_after:
                return (
                    f"\n⚠️ Con esto te pasaste de tu tope de {name}: "
                    f"{_money(spent_after)} de {_money(limit)}."
                )
            if before < threshold_amt <= spent_after:
                pct = round(status.percentage)
                return (
                    f"\n⚠️ Ojo: vas al {pct}% de tu tope de {name} "
                    f"({_money(spent_after)} de {_money(limit)})."
                )
            return ""
        except Exception as exc:  # noqa: BLE001 - best-effort nudge, never fail registration
            logger.warning("Budget nudge failed", error=str(exc), user_id=user_id)
            return ""

    async def _resolve_card_id(
        self, args: dict[str, Any], payment_method: PaymentMethod | None, user_id: UserId
    ) -> tuple[CreditCard | None, str | None]:
        """Resolve the credit card a charge belongs to.

        Returns ``(card, clarification)`` (the card object, so the caller can also
        derive the budget/impact date from its cycle). By name if the user said
        one; otherwise, if the user has exactly one card, use it automatically.
        When the charge is on credit and the card is ambiguous (several cards and
        no name, or a name we can't find), returns a clarification question and no
        card, so the caller asks which card instead of leaving the charge unlinked.
        """
        card_name = str(args.get("card_name", "")).strip()
        # Naming a card means it's a card charge, even if the model didn't also set
        # payment_method='credito' — otherwise the charge would be left unlinked.
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

    async def _query(self, args: dict[str, Any], user_id: UserId) -> str:
        card_id, card_error = await self._resolve_query_card(args, user_id)
        if card_error is not None:
            return card_error
        # Fetch a wide page with the DB-side filters, then narrow by month and
        # payment method in Python (PostgREST can't range-filter dates here). The
        # whole set is returned so month questions aren't truncated to one page.
        items, _total = await self._service.list_transactions(
            user_id,
            page=1,
            page_size=ANALYZE_FETCH_LIMIT,
            transaction_type=_to_type(args.get("transaction_type")),
            category=_to_category(args.get("category")),
            card_id=card_id,
        )
        period = str(args.get("period", "")).strip().lower()
        if period:
            # Reject unrecognized months so we don't silently return the current
            # month (resolve_period's lenient fallback) and mislead the user.
            if period not in _NAMED_PERIODS and not _MONTH_ARG_RE.match(period):
                return (
                    "¿De qué mes? Dímelo como '2026-06' (año-mes) o "
                    "'este_mes' / 'mes_pasado' / 'todo'."
                )
            start, end = resolve_period(period, today=current_today())
            items = [t for t in items if start <= t.transaction_date <= end]
        payment = _to_payment_method(args.get("payment_method"))
        if payment is PaymentMethod.EFECTIVO:
            # Cash = tagged 'efectivo', or untagged with no card linked.
            items = [
                t
                for t in items
                if t.payment_method == PaymentMethod.EFECTIVO
                or (t.payment_method is None and t.card_id is None)
            ]
        elif payment is PaymentMethod.CREDITO:
            # Credit = tagged 'credito', or untagged but linked to a card.
            items = [
                t
                for t in items
                if t.payment_method == PaymentMethod.CREDITO
                or (t.payment_method is None and t.card_id is not None)
            ]
        if not items:
            return "No se encontraron transacciones con esos filtros."

        # Map card_id -> name so the reply names the card (a charge shows "crédito,
        # tarjeta Nu"), not just its payment method — otherwise the agent can't tell
        # which card a charge belongs to. Skip the lookup for card-less results.
        card_names = (
            await self._card_name_map(user_id) if any(t.card_id for t in items) else {}
        )
        # No ids: update/delete resolve the transaction by description/amount, so
        # the agent never has to copy a UUID (LLMs mangle them).
        shown = sorted(items, key=lambda t: t.transaction_date, reverse=True)
        lines = [
            f"- {t.description}: ${t.amount} ({t.category}, {t.transaction_date}"
            + (f", {t.payment_method.value}" if t.payment_method else "")
            + (
                f", tarjeta {card_names[t.card_id]}"
                if t.card_id is not None and t.card_id in card_names
                else ""
            )
            + ")"
            for t in shown[:QUERY_DISPLAY_LIMIT]
        ]
        total_amount = sum((t.amount for t in items), Decimal("0"))
        capped = (
            f" (muestro las {QUERY_DISPLAY_LIMIT} más recientes)"
            if len(items) > QUERY_DISPLAY_LIMIT
            else ""
        )
        header = f"{len(items)} transacción(es) por ${total_amount:,.0f} en total{capped}:"
        return header + "\n" + "\n".join(lines)

    async def _card_name_map(self, user_id: UserId) -> dict[str, str]:
        """Map each of the user's card ids to its name (empty if no card service)."""
        if self._cards is None:
            return {}
        cards = await self._cards.list_cards(user_id)
        return {card.id: card.name for card in cards}

    async def _resolve_query_card(
        self, args: dict[str, Any], user_id: UserId
    ) -> tuple[str | None, str | None]:
        """Resolve a ``card_name`` filter to a card id. Returns ``(card_id, error)``."""
        card_name = str(args.get("card_name", "")).strip()
        if not card_name or self._cards is None:
            return None, None
        card = await self._cards.resolve_by_name(card_name, user_id)
        if card is None:
            return None, f"No encontré una tarjeta que coincida con '{card_name}'."
        return card.id, None

    async def _delete_movements(self, args: dict[str, Any], user_id: UserId) -> str:
        # Resolve the optional card filter.
        card: CreditCard | None = None
        card_name = str(args.get("card_name", "")).strip()
        if card_name:
            if self._cards is None:
                return "No tienes tarjetas configuradas."
            card = await self._cards.resolve_by_name(card_name, user_id)
            if card is None:
                return f"No encontré una tarjeta que coincida con '{card_name}'."

        category = _to_category(args.get("category"))

        # Resolve the time scope: a named/YYYY-MM period, or an explicit date range.
        period = str(args.get("period", "")).strip().lower()
        start = _opt_date(args.get("start_date"))
        end = _opt_date(args.get("end_date"))
        scope_label = ""
        if period:
            if period not in _NAMED_PERIODS and not _MONTH_ARG_RE.match(period):
                return "¿De qué período? Dime un mes ('2026-07'), 'todo', o un rango de fechas."
            start, end = resolve_period(period, today=current_today())
            scope_label = period_label(period)
        elif (start is None) != (end is None):
            return "Para un rango necesito AMBAS fechas: inicio y fin (YYYY-MM-DD)."
        elif start is not None and end is not None:
            scope_label = f"{start} a {end}"

        # Destructive: always require a time scope so an omitted arg can't wipe all
        # history. Use 'todo' explicitly to clear everything for a card/category.
        if start is None or end is None:
            return (
                "¿De qué período? Dime un mes (p. ej. '2026-07'), un rango de fechas, "
                "o 'todo' para borrar sin límite de fecha."
            )

        deleted = await self._service.delete_movements(
            user_id,
            card_id=card.id if card else None,
            category=category,
            period_start=start,
            period_end=end,
        )
        filters = [
            label
            for label in (
                f"tarjeta {card.name}" if card else "",
                f"categoría {category}" if category else "",
                scope_label,
            )
            if label
        ]
        scope = ", ".join(filters)
        if deleted == 0:
            return f"No encontré movimientos con esos filtros ({scope})."
        logger.info("Deleted movements", scope=scope, count=deleted, user_id=user_id)
        return f"🗑️ Borré {deleted} movimiento(s) ({scope})."

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
        top = top_expenses(transactions, TOP_EXPENSES_LIMIT)
        return _format_analysis(period, income, expenses, by_category, patterns, top)

    async def _update(self, args: dict[str, Any], user_id: UserId) -> str:
        target = await self._resolve_transaction(args, user_id)
        if target is None:
            return "No encontré esa transacción. ¿Puedes darme más detalles (monto o fecha)?"
        # Fold a re-categorization onto an existing category when it's a close match.
        new_category = _to_category(args.get("new_category"))
        if new_category is not None:
            new_category = await self._service.resolve_category(new_category, user_id)
        try:
            updated = await self._service.update_transaction(
                target.id,
                user_id,
                amount=_opt_decimal(args.get("new_amount")),
                description=_opt_str(args.get("new_description")),
                category=new_category,
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
        # A list of descriptors deletes several specific gastos at once.
        items = args.get("items")
        if isinstance(items, list) and items:
            return await self._delete_many(items, user_id)

        description = str(args.get("description", "")).lower().strip()
        if not description:
            return "¿Qué gasto quieres eliminar? Dame la descripción (y el monto o la fecha si ayuda)."
        # Installment rows of one purchase share a created_at, so they cluster in
        # this page; a purchase older than the cap can't be resolved (fine here).
        pool, _ = await self._service.list_transactions(
            user_id, page=1, page_size=ANALYZE_FETCH_LIMIT
        )
        group = _resolve_delete_group(
            pool,
            description,
            _opt_decimal(args.get("amount")),
            _opt_date(args.get("transaction_date")),
        )
        if group is None:
            return "No encontré ese gasto (revisa la descripción o el monto)."
        removed = await self._delete_group(group, user_id)
        if removed == 0:
            return "No encontré ese gasto (quizás ya no existe)."
        if len(group) > 1:
            base = _cuota_base(group[0].description)
            total = sum((t.amount for t in group), Decimal("0"))
            return f"🗑️ Eliminé la compra a cuotas «{base}»: {removed} cuota(s) por ${total} en total."
        tx = group[0]
        return f"🗑️ Eliminé: {tx.description} — ${tx.amount} ({tx.transaction_date})."

    async def _delete_many(self, items: list[Any], user_id: UserId) -> str:
        # Resolve every descriptor against ONE fetch, dedupe by id (installment
        # groups expand), then delete all concurrently.
        pool, _ = await self._service.list_transactions(
            user_id, page=1, page_size=ANALYZE_FETCH_LIMIT
        )
        targets: dict[str, Transaction] = {}
        not_found: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            label = str(item.get("description", "")).strip()
            resolved = _resolve_delete_group(
                pool,
                label.lower(),
                _opt_decimal(item.get("amount")),
                _opt_date(item.get("transaction_date")),
            )
            if resolved is None:
                if label:
                    not_found.append(label)
                continue
            for tx in resolved:
                targets[tx.id] = tx

        if not targets:
            return "No encontré ninguno de esos gastos (revisa las descripciones o montos)."
        removed = await self._delete_group(list(targets.values()), user_id)
        message = f"🗑️ Eliminé {removed} movimiento(s)."
        if not_found:
            message += f" No encontré: {', '.join(not_found)}."
        return message

    async def _delete_group(self, group: list[Transaction], user_id: UserId) -> int:
        """Delete every row in a group concurrently; tolerate already-gone rows."""
        semaphore = asyncio.Semaphore(DELETE_CONCURRENCY)

        async def _delete_one(transaction_id: TransactionId) -> Transaction:
            async with semaphore:
                return await self._service.delete_transaction(transaction_id, user_id)

        results = await asyncio.gather(
            *(_delete_one(tx.id) for tx in group),
            return_exceptions=True,
        )
        removed = 0
        for result in results:
            if isinstance(result, TransactionNotFoundError):
                continue
            if isinstance(result, BaseException):
                raise result
            removed += 1
        return removed

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

        items, _ = await self._service.list_transactions(
            user_id, page=1, page_size=ANALYZE_FETCH_LIMIT
        )
        matches = [
            t
            for t in items
            if _matches_term(t, description)
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
    today = current_today()
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
    top: list[tuple[str, float, str]],
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
    if top:
        lines.append("")
        lines.append("Mayores gastos individuales (usa sus descripciones para dar detalle):")
        lines.extend(
            f"- {desc}: ${amount:,.2f} ({get_category_label(category)})"
            for desc, amount, category in top
        )
    if patterns:
        lines.append("")
        lines.append("Patrones detectados:")
        lines.extend(f"- {pattern}" for pattern in patterns)
    return "\n".join(lines)


def _money(value: Decimal) -> str:
    """Format an amount like the rest of the tool: thousands, no decimals."""
    return f"${value:,.0f}"


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
            return current_today()
    return current_today()


def _credit_budget_date(card: CreditCard | None, transaction_date: date) -> date:
    """Budget/impact date for a charge.

    For a credit charge, the payment date of the statement that contains it
    (derived from the card's cutoff/payment cycle) — so a purchase after the
    cutoff lands on the month it is actually paid. For cash/debit (no card),
    the purchase date itself.
    """
    if card is None:
        return transaction_date
    _, cycle_end = compute_cycle(card.cutoff_day, transaction_date)
    return next_payment_date(card.payment_day, cycle_end)


def _budget_month_label(value: date) -> str:
    """Spanish 'mes de año' label for the budget month (e.g. 'septiembre de 2026')."""
    return period_label(f"{value.year}-{value.month:02d}")


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
