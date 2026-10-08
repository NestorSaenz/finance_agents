"""Credit-card tools for conversational data operations.

Thin wrappers over ``CreditCardService`` exposed to the LLM. ``user_id`` is
supplied by the toolkit from the authenticated context at dispatch time and is
NEVER part of the tool schema. Cards are referenced by NAME (no ids exposed).
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import CardNotFoundError, DatabaseError, NoActiveTurnError
from app.core.logging import get_logger
from app.shared.clock import current_today
from app.shared.periods import is_valid_period, period_label, resolve_period
from app.shared.types import UserId
from app.src.cards.interfaces import CardScheduleChangeServiceABC, CreditCardServiceABC
from app.src.cards.models import (
    CardPaymentCreate,
    CardScheduleChange,
    CreditCard,
    CreditCardCreate,
    CreditCardStatus,
    ScheduleChangeOutcome,
)

logger = get_logger(__name__)

CREATE_CARD_TOOL = "create_card"
QUERY_CARDS_TOOL = "query_cards"
PAY_CARD_TOOL = "pay_card"
REMOVE_CARD_PAYMENT_TOOL = "remove_card_payment"
UPDATE_CARD_TOOL = "update_card"
CONFIRM_CARD_CHANGE_TOOL = "confirm_card_change"
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
                "Consulta las tarjetas del usuario: días de corte y pago, deuda TOTAL, "
                "crédito disponible, cuánto hay que pagar en la próxima fecha (y de qué "
                "corte) y lo que lleva el ciclo abierto. Sin 'period' informa el estado "
                "ACTUAL ('¿cómo van mis tarjetas?', '¿cuánto debo pagar de la Visa?', "
                "'¿cuándo pago la tarjeta?'). Con 'period' "
                "informa lo gastado con cada tarjeta en ESE periodo ('¿cuánto gasté con "
                "la Visa el mes pasado?', '¿con qué tarjeta gasto más históricamente?' "
                "→ period='todo')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": (
                            "Periodo a consultar: 'este_mes', 'mes_pasado', 'todo' o "
                            "'YYYY-MM' (p. ej. '2026-06'). Omítelo para el ciclo actual."
                        ),
                    },
                },
            },
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
            "name": REMOVE_CARD_PAYMENT_TOOL,
            "description": (
                "Borra un pago/abono mal registrado de una tarjeta (por su monto y, si "
                "hace falta, su fecha y/o la tarjeta). Es lo contrario de pay_card. NO "
                "elimina la tarjeta (eso es delete_card). Úsala SOLO tras confirmar con "
                "el usuario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Monto del pago a borrar, mayor a 0",
                    },
                    "card_name": {
                        "type": "string",
                        "description": (
                            "Nombre de la tarjeta; úsalo para desambiguar si hay pagos "
                            "del mismo monto en varias tarjetas (opcional)"
                        ),
                    },
                    "payment_date": {
                        "type": "string",
                        "description": (
                            "Fecha del pago YYYY-MM-DD; úsala SOLO para desambiguar si "
                            "hay varios pagos del mismo monto"
                        ),
                    },
                },
                "required": ["amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": UPDATE_CARD_TOOL,
            "description": (
                "Cambia nombre/cupo de inmediato. Para día de corte/pago SOLO crea una "
                "propuesta (no la aplica): muéstrala y pregunta ('Periodo del 21 ago al "
                "20 sep' → corte 20; 'desde el 21' → 20). La identificas por su NOMBRE "
                "actual. 'Periodo de facturación', 'ciclo', 'fecha de corte' y 'cierre' "
                "son el DÍA DE CORTE; 'fecha límite de pago' es el día de pago. Safi "
                "cambia SU registro de la tarjeta; el corte real lo define el banco: "
                "NUNCA digas 'solo el banco puede'. No cambies new_payment_day salvo que "
                "lo pida."
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
                        "description": (
                            "Nuevo día de corte, 1-31 (opcional). Equivale a 'periodo de "
                            "facturación', 'ciclo', 'fecha de corte' o 'cierre'; si dan "
                            "un periodo, es su último día"
                        ),
                    },
                    "new_payment_day": {
                        "type": "integer",
                        "description": (
                            "Nuevo día de pago o fecha límite de pago, 1-31 (opcional)"
                        ),
                    },
                },
                "required": ["card_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": CONFIRM_CARD_CHANGE_TOOL,
            "description": (
                "Aplica el cambio de corte/pago propuesto en tu turno anterior. Úsala "
                "SOLO si el mensaje ACTUAL del usuario acepta esa propuesta."
            ),
            "parameters": {"type": "object", "properties": {}},
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
    """Exposes credit-card tools to the LLM and dispatches its tool calls.

    Known limit: cutoff/payment-day changes are gated in code only through
    ``update_card`` + ``confirm_card_change``. A user could still change the days via
    ``delete_card`` + ``create_card``, which is guarded only by the prompt (delete_card
    asks for confirmation).
    """

    def __init__(self, service: CreditCardServiceABC, schedule: CardScheduleChangeServiceABC) -> None:
        self._service = service
        self._schedule = schedule

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return CARD_TOOL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        if name == CREATE_CARD_TOOL:
            return await self._create(arguments, user_id)
        if name == QUERY_CARDS_TOOL:
            return await self._query(arguments, user_id)
        if name == PAY_CARD_TOOL:
            return await self._pay(arguments, user_id)
        if name == REMOVE_CARD_PAYMENT_TOOL:
            return await self._remove_payment(arguments, user_id)
        if name == UPDATE_CARD_TOOL:
            return await self._update(arguments, user_id)
        if name == CONFIRM_CARD_CHANGE_TOOL:
            return await self._confirm_change(user_id)
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

    async def _query(self, args: dict[str, Any], user_id: UserId) -> str:
        # Anchor the cycle/next-payment on the user's local day, not UTC, so a
        # near-midnight query doesn't report the next cycle a day early.
        today = current_today()
        period = str(args.get("period", "")).strip().lower()
        # Reject an unrecognized period instead of silently answering for the
        # current month (resolve_period's lenient fallback).
        if period and not is_valid_period(period):
            return (
                "¿De qué periodo? Dímelo como '2026-06' (año-mes) o "
                "'este_mes' / 'mes_pasado' / 'todo'."
            )
        # A period reconstructs each card AS OF that window's end: `spent_cycle`
        # then carries the period's charges instead of the current cycle's. The
        # charges are attributed by transaction_date (purchase date) — the same
        # field the billing cycle and the dashboard's monthly card view use, so
        # chat and dashboard never disagree about what a card spent in a month.
        start, end = resolve_period(period, today=today) if period else (None, None)
        statuses = await self._service.get_all_status(
            user_id, as_of=today, period_start=start, period_end=end
        )
        if not statuses:
            return "No tienes tarjetas registradas."
        if period:
            # A month spans two statements: no single due date/amount applies, so
            # the historical view never claims one.
            lines = [_historical_card_line(s, period_label(period)) for s in statuses]
            header = (
                f"{len(statuses)} tarjeta(s) — gasto de {period_label(period)} "
                "(la deuda total y el disponible son los del cierre de ese periodo):"
            )
        else:
            lines = [_live_card_line(s) for s in statuses]
            header = (
                f"{len(statuses)} tarjeta(s) — hoy {today}. La deuda TOTAL incluye el "
                "ciclo abierto: NO es lo que se paga en la próxima fecha (eso es "
                "'A pagar el'):"
            )
        return f"{header}\n" + "\n".join(lines)

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
        today = current_today()
        payment_date = _opt_date(args.get("payment_date")) or today
        await self._service.register_payment(
            card.id, user_id, CardPaymentCreate(amount=amount, payment_date=payment_date)
        )
        when = "" if payment_date == today else f" ({payment_date})"
        return f"✅ Registré tu pago de ${amount} a '{card.name}'{when}."

    async def _remove_payment(self, args: dict[str, Any], user_id: UserId) -> str:
        try:
            amount = _to_decimal(args.get("amount"))
        except ValueError:
            return "No pude borrar el pago: el monto no es válido."
        if amount <= 0:
            return "El monto del pago a borrar debe ser mayor a 0."

        # Optional card filter: resolve the name so the message is precise and the
        # match is scoped to that card.
        name = str(args.get("card_name", "")).strip()
        card_id: str | None = None
        card_label = ""
        if name:
            card = await self._service.resolve_by_name(name, user_id)
            if card is None:
                return f"No encontré una tarjeta llamada '{name}'. ¿Cuál es el nombre exacto?"
            card_id = card.id
            card_label = f" de «{card.name}»"

        payment_date = _opt_date(args.get("payment_date"))
        removed = await self._service.remove_payment(
            user_id, amount, payment_date=payment_date, card_id=card_id
        )
        if removed is None:
            when = f" del {payment_date}" if payment_date else ""
            return (
                f"No encontré un pago de ${amount}{when}{card_label}. "
                "Revisa el monto (y la fecha) del pago que quieres borrar."
            )
        return f"🗑️ Borré el pago de ${removed.amount}{card_label} ({removed.payment_date})."

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

        # Name/limit are applied now; cutoff/payment days only become a PROPOSAL that
        # confirm_card_change applies after the user's later "sí" (enforced in code).
        direct = ""
        heading = card.name
        if new_name is not None or new_limit is not None:
            try:
                updated = await self._service.update_card(
                    card.id, user_id, name=new_name, credit_limit=new_limit
                )
            except CardNotFoundError:
                return "No encontré esa tarjeta para actualizar."
            heading = updated.name
            changes, _ = _update_changes(card, updated)
            direct = f"✏️ Actualicé tu tarjeta {updated.name}: {'; '.join(changes)}." if changes else ""

        proposal = ""
        if new_cutoff is not None or new_payment is not None:
            proposal = await self._propose_schedule(card, heading, user_id, new_cutoff, new_payment)

        if direct and proposal == _SCHEDULE_UNAVAILABLE:
            proposal = _SCHEDULE_NOT_SAVED
        result = " ".join(part for part in (direct, proposal) if part)
        return result or f"La tarjeta {heading} ya tenía esos datos; no hubo cambios."

    async def _propose_schedule(
        self,
        card: CreditCard,
        heading: str,
        user_id: UserId,
        cutoff: int | None,
        payment: int | None,
    ) -> str:
        """Store a schedule proposal; '' when the days already match the card."""
        try:
            proposal = await self._schedule.propose(card, user_id, cutoff, payment)
        except (NoActiveTurnError, DatabaseError) as e:
            logger.warning("Could not store card schedule proposal", error=str(e))
            return _SCHEDULE_UNAVAILABLE
        if proposal is None:
            return ""
        summary = _proposal_summary(heading, proposal.change)
        if proposal.already_pending:
            return (
                f"Ya está propuesto: {summary}. Si el usuario ya aceptó, llama a "
                "confirm_card_change; si no, pregúntale «¿Lo cambio?»."
            )
        return (
            f"PROPUESTA (aún NO aplicada): {summary}. "
            "Pregunta al usuario «¿Lo cambio?». Si en su próximo mensaje acepta, "
            "llama a confirm_card_change."
        )

    async def _confirm_change(self, user_id: UserId) -> str:
        try:
            result = await self._schedule.confirm(user_id)
        except (NoActiveTurnError, DatabaseError) as e:
            logger.warning("Could not confirm card schedule change", error=str(e))
            return _SCHEDULE_UNAVAILABLE
        if result.outcome is ScheduleChangeOutcome.NONE_PENDING:
            return _NONE_PENDING
        if result.outcome is ScheduleChangeOutcome.STALE:
            return _STALE_SCHEDULE
        if result.before is None or result.after is None:
            return "No encontré esa tarjeta para actualizar."
        changes, schedule_changed = _update_changes(result.before, result.after)
        if not changes:
            return f"La tarjeta {result.after.name} ya tenía esos datos; no hubo cambios."
        note = f" {_FROZEN_CHARGES_NOTE}" if schedule_changed else ""
        return f"✏️ Actualicé tu tarjeta {result.after.name}: {'; '.join(changes)}.{note}"

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


_FROZEN_CHARGES_NOTE = (
    "Los cargos ya registrados conservan el mes de presupuesto que se les asignó con "
    "el día de corte/pago anterior."
)


_SCHEDULE_UNAVAILABLE = (
    "No pude guardar ni aplicar el cambio de corte/pago ahora; no se cambió nada. "
    "Inténtalo de nuevo en un momento."
)
_SCHEDULE_NOT_SAVED = "El cambio de corte/pago no se guardó; inténtalo de nuevo."
_NONE_PENDING = (
    "No hay un cambio de corte/pago aceptado por el usuario (se propone y se confirma "
    "en mensajes distintos; o expiró). Vuelve a proponerlo con update_card."
)
_STALE_SCHEDULE = "Los días de la tarjeta cambiaron desde la propuesta; vuelve a proponer."


def _proposal_summary(card_name: str, change: CardScheduleChange) -> str:
    """Render the (not yet applied) change; shows the unchanged day for context."""
    parts = [
        f"{label} {old} → {new}"
        for label, old, new in (
            ("corte", change.prev_cutoff_day, change.cutoff_day),
            ("pago", change.prev_payment_day, change.payment_day),
        )
        if new is not None
    ]
    kept = (
        f", el día de pago sigue el {change.prev_payment_day}"
        if change.payment_day is None
        else f", el día de corte sigue el {change.prev_cutoff_day}"
        if change.cutoff_day is None
        else ""
    )
    return f"{card_name}: {' y '.join(parts)}{kept}"


def _update_changes(before: CreditCard, after: CreditCard) -> tuple[list[str], bool]:
    """Return 'old → new' for each changed field, and whether cutoff/payment day changed."""
    schedule = [
        f"{label}: día {old} → {new}"
        for label, old, new in (
            ("corte", before.cutoff_day, after.cutoff_day),
            ("pago", before.payment_day, after.payment_day),
        )
        if old != new
    ]
    others = [
        *([f"nombre: {before.name} → {after.name}"] if before.name != after.name else []),
        *(
            [f"cupo: ${before.credit_limit} → ${after.credit_limit}"]
            if before.credit_limit != after.credit_limit
            else []
        ),
    ]
    return [*others, *schedule], bool(schedule)


def _card_heading(status: CreditCardStatus) -> str:
    card = status.card
    return f"- {card.name} (corte día {card.cutoff_day}, pago día {card.payment_day})"


def _live_card_line(status: CreditCardStatus) -> str:
    """Live line: total debt, what's due next (and for which cutoff), open cycle."""
    s = status
    if s.statement_amount is not None:
        covered = " (ya cubierto)" if s.statement_amount == 0 else ""
        due = (
            f"A pagar el {s.next_payment_date}: ${s.statement_amount}{covered} "
            f"(corte {s.statement_start}–{s.statement_end})."
        )
    else:
        # The upcoming due date is the open cycle's: its amount isn't final yet.
        due = (
            f"A pagar el {s.next_payment_date}: monto aún no definido (el ciclo "
            f"{s.cycle_start}–{s.cycle_end} sigue abierto)."
        )
    open_cycle = (
        f"En el ciclo abierto {s.cycle_start}–{s.cycle_end} (se paga el "
        f"{s.cycle_payment_date}): ${s.spent_cycle}."
    )
    overdue = (
        f" Vencido sin pagar (de cortes anteriores ya vencidos): ${s.overdue_amount}."
        if s.overdue_amount
        else ""
    )
    return (
        f"{_card_heading(s)}: deuda TOTAL ${s.balance} de ${s.card.credit_limit} "
        f"(disponible ${s.available}). {due} {open_cycle}{overdue}"
    )


def _historical_card_line(status: CreditCardStatus, label: str) -> str:
    """Historical line: month-end total debt and the month's spend, no due claim."""
    s = status
    return (
        f"{_card_heading(s)}: deuda TOTAL ${s.balance} de ${s.card.credit_limit} "
        f"(disponible ${s.available}); gastado en {label} ${s.spent_cycle}"
    )


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
