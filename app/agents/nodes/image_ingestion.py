"""Image ingestion: extract financial movements from a photo/screenshot.

The user attaches an image of their spreadsheet (or a receipt). A vision model
extracts the movements as structured rows; we turn that into a Spanish proposal
that lists what was read and asks the user to confirm BEFORE anything is
registered. Every line is first compared with the user's records, so only what is
still missing is proposed (or, when they asked to "validate", reported on). On the
user's confirmation, the normal tool agent reads the proposal from the conversation
history and registers each movement — so the extracted amounts are shown for review
first, never written blindly.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Final

import httpx
from postgrest.exceptions import APIError
from pydantic import BaseModel, ValidationError

from app.core.exceptions import DatabaseError
from app.core.logging import get_logger
from app.shared.clock import current_today, resolve_statement_date
from app.shared.interfaces.llm import (
    ImagePart,
    LLMConfig,
    LLMInterface,
    Message,
    MessageRole,
)
from app.shared.text_match import normalize
from app.shared.types import IngestionIntent, StatementLineKind, UserId
from app.src.analysis.interfaces import StatementReconcilerABC
from app.src.analysis.models import ReconciledLine, ReconciliationResult, StatementLine

logger = get_logger(__name__)

EXTRACTION_TEMPERATURE: Final[float] = 0.0
EXTRACTION_MAX_TOKENS: Final[int] = 2048
# Cap listed rows so the confirmable proposal stays complete: only listed rows can
# be registered on confirmation, so this must be generous (a single image rarely
# holds more legible rows). If exceeded, the user is told the rest need another image.
MAX_LISTED_MOVEMENTS: Final[int] = 200
# One question at most (the payment method/card): every extra question made the user
# answer line by line, and categories are inferred by Safi, never asked.
MAX_QUESTIONS: Final[int] = 1

# Marker phrases shared with the tool agent's prompt: the proposal's registrable block
# starts with the header and ends with the confirm question, which is how a "sí" is
# recognized as a batch registration. Keep these as the single source of truth for both
# sides. Lines ABOVE the header (already registered) must never be registered.
PROPOSAL_HEADER: Final[str] = "Faltan por registrar:"
PROPOSAL_CONFIRM: Final[str] = "¿Los registro tal cual?"
_CATEGORIZE_NOTE: Final[str] = "Los categorizo yo y te muestro cómo quedaron."
_ALL_REGISTERED: Final[str] = "Todos ya están registrados ✅"
_COULD_NOT_COMPARE_VERIFY: Final[str] = (
    "No pude compararlos con tus registros; inténtalo de nuevo en un momento."
)
_COULD_NOT_COMPARE_REGISTER: Final[str] = (
    "Ojo: no pude revisar si alguno ya estaba registrado."
)
_AUTO_CATEGORY: Final[str] = "categoría automática"

# Words in the user's note that ask to CHECK the document against their records instead
# of registering it. Matched on accent-stripped lowercase text; verify wins over register
# ("revisa y registra los que falten" is still a check first).
VERIFY_KEYWORDS: Final[tuple[str, ...]] = (
    "valida",
    "validar",
    "verifica",
    "revisa",
    "comprueba",
    "chequea",
    "confirma si",
    "ya estan registrad",
    "estan registrad",
    "cuales faltan",
    "falta alguno",
    "faltan",
    "no he registrado",
    "sin registrar",
    "por registrar",
)

# A credit-card statement shows the payment received as a credit line; it is already
# in the user's card payments, so it must never be proposed as income.
# A bare "abono" is NOT one: refunds ("Abono por devolución") and savings deposits use it.
CARD_PAYMENT_KEYWORDS: Final[tuple[str, ...]] = (
    "gracias por tu pago",
    "pago recibido",
    "pago tarjeta",
    "pago de tarjeta",
    "pago a tarjeta",
    "abono a tarjeta",
    "abono tarjeta",
)

_MONTHS_ES: Final[tuple[str, ...]] = (
    "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic",
)  # fmt: skip

# Asked (deterministically) when an expense has no payment method and the model
# didn't already ask: a factura rarely states cash vs. credit, but Safi needs it.
_PAYMENT_QUESTION: Final[str] = (
    "¿Cómo lo pagaste? Dime si fue en efectivo o con tarjeta de crédito."
)
# If any of these appear in the model's questions, it already covers payment method.
_PAYMENT_KEYWORDS: Final[tuple[str, ...]] = (
    "efectivo",
    "crédito",
    "credito",
    "tarjeta",
    "pagaste",
    "pagó",
    "método de pago",
)
# Questions about categories are dropped: Safi categorizes by itself.
_CATEGORY_MENTIONS: Final[tuple[str, ...]] = ("categoria", "clasific")

# Failures reading the user's records that must not break the upload: the proposal
# is then shown unreconciled, with a notice.
_RECONCILE_FAILURES: Final = (DatabaseError, APIError, httpx.HTTPError)

_SYSTEM_PROMPT: Final[str] = (
    "Eres un asistente financiero que lee una imagen o un PDF (foto o captura de un "
    "Excel, una tabla o un recibo) y extrae los movimientos de dinero. Responde ÚNICAMENTE "
    "con un objeto JSON válido, sin texto adicional ni ```.\n\n"
    "Formato exacto:\n"
    "{\n"
    '  "movements": [\n'
    "    {\n"
    '      "description": "texto corto del movimiento",\n'
    '      "amount": number,   // en pesos, sin separadores. "200.000" = 200000\n'
    '      "transaction_type": "expense" | "income" | "card_payment",\n'
    '      "date": "YYYY-MM-DD" | null,\n'
    '      "category": "texto libre" | null,  // usa las categorías propias del usuario\n'
    '      "payment_method": "efectivo" | "credito" | null,\n'
    '      "card": "nombre de la tarjeta" | null  // si la nota del usuario indica una\n'
    "    }\n"
    "  ],\n"
    '  "questions": ["preguntas sobre celdas ambiguas"],\n'
    '  "notes": "observaciones" | null\n'
    "}\n\n"
    "Reglas:\n"
    "- Extrae el MÁXIMO de movimientos que veas.\n"
    "- Contexto colombiano: los montos suelen escribirse con puntos de miles "
    "('200.000' significa 200000, no 200).\n"
    "- Respeta las CATEGORÍAS que aparezcan en el documento aunque no sean estándar "
    "(p. ej. 'jardinería', 'diezmo'); no las fuerces a otras.\n"
    "- Propón la categoría del gasto si es evidente; si no, déjala en null SIN hacer "
    "pregunta (el sistema la deduce después). NO inventes una categoría dudosa.\n"
    "- PAGO A LA TARJETA: en el extracto de una tarjeta de crédito, las líneas como "
    "'Gracias por tu pago', 'Pago recibido', 'Abono' o 'Pago tarjeta' son un pago hecho "
    "a la tarjeta, NO un ingreso: usa transaction_type='card_payment'.\n"
    "- EXTRACTO DE TARJETA DE CRÉDITO: si el encabezado o el contexto muestra una "
    "tarjeta de crédito (Nu, 'tarjeta de crédito', 'Gracias por tu pago'), TODOS los "
    "cargos son payment_method='credito' con card igual al nombre de esa tarjeta.\n"
    "- Si una celda es ambigua o dudosa, incluye tu mejor interpretación (no hagas "
    "preguntas por línea).\n"
    "- MÉTODO DE PAGO: una factura casi nunca dice cómo se pagó. Si el documento no "
    "indica claramente 'efectivo' o 'crédito', deja payment_method en null y AÑADE en "
    "'questions' UNA sola pregunta para saber cómo lo pagó el usuario.\n"
    "- NOTA DEL USUARIO: si la nota indica cómo pagó o con qué tarjeta (p. ej. 'son de "
    "mi tarjeta Nu', 'todo a crédito'), aplícalo a TODOS los movimientos: pon "
    "payment_method='credito' y card con el nombre de la tarjeta. Así NO vuelvas a "
    "preguntar el método ni la tarjeta.\n"
    "- Si no hay fecha, usa null (se asumirá la fecha de hoy).\n"
    "- Si el extracto no muestra el año, usa el año de hoy (o el anterior si la fecha "
    "quedaría en el futuro). Nunca uses un año anterior al año pasado.\n"
    "- Si el documento no contiene movimientos financieros, devuelve movements vacío."
)

_USER_PROMPT: Final[str] = (
    "Extrae los movimientos financieros de este documento y devuélvelos en el JSON pedido."
)


class ExtractedMovement(BaseModel):
    """A single movement read from the image (pre-registration)."""

    description: str
    amount: Decimal
    # "expense" | "income" | "card_payment" (see ``StatementLineKind``).
    transaction_type: str = StatementLineKind.EXPENSE
    date: str | None = None
    category: str | None = None
    payment_method: str | None = None
    card: str | None = None  # credit card name, if the user's note said one


class ExtractionResult(BaseModel):
    """The structured result of reading an image."""

    movements: list[ExtractedMovement] = []
    questions: list[str] = []
    notes: str | None = None


def detect_ingestion_intent(note: str) -> IngestionIntent:
    """VERIFY when the user's note asks to check the document, else REGISTER."""
    text = normalize(note)
    if any(keyword in text for keyword in VERIFY_KEYWORDS):
        return IngestionIntent.VERIFY
    return IngestionIntent.REGISTER


class ImageIngestionServiceABC(ABC):
    """Contract for reading an image and proposing the movements to register."""

    @abstractmethod
    async def propose(
        self,
        image: bytes,
        mime_type: str,
        user_id: UserId,
        user_context: str = "",
        user_note: str = "",
    ) -> str:
        """Extract movements from ``image`` and return a Spanish report/proposal."""


class ImageIngestionService(ImageIngestionServiceABC):
    """Reads an image with a vision LLM and proposes the movements to register."""

    def __init__(self, llm: LLMInterface, reconciler: StatementReconcilerABC) -> None:
        self._llm = llm
        self._reconciler = reconciler

    async def propose(
        self,
        image: bytes,
        mime_type: str,
        user_id: UserId,
        user_context: str = "",
        user_note: str = "",
    ) -> str:
        """Extract movements from ``image`` and return a Spanish report/proposal."""
        today = current_today()
        system_content = f"{_SYSTEM_PROMPT}\n\nFecha de hoy: {today.isoformat()}."
        if user_context:
            system_content = f"{system_content}\n\nContexto del usuario:\n{user_context}"

        # The user's note may state how these were paid / which card, which the
        # extractor applies to all movements (so registration doesn't re-ask).
        user_content = _USER_PROMPT
        if user_note:
            user_content = f"{_USER_PROMPT}\n\nNota del usuario sobre estos movimientos: {user_note}"

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_content),
            Message(
                role=MessageRole.USER,
                content=user_content,
                images=[ImagePart(data=image, mime_type=mime_type)],
            ),
        ]
        config = LLMConfig(
            temperature=EXTRACTION_TEMPERATURE, max_tokens=EXTRACTION_MAX_TOKENS
        )

        try:
            response = await self._llm.generate(messages=messages, config=config)
            result = _parse_extraction(response.content)
        except Exception as e:  # noqa: BLE001 - vision/LLM boundary: degrade gracefully.
            logger.error("Image ingestion failed", error=str(e))
            return (
                "No pude leer el archivo con claridad. ¿Puedes enviarlo de nuevo, "
                "más nítido o mejor encuadrado?"
            )

        result = _reclassify_card_payments(_with_resolved_dates(result, today))
        intent = detect_ingestion_intent(user_note)
        logger.info(
            "Image ingestion parsed", movements=len(result.movements), intent=intent.value
        )
        reconciliation = await self._reconcile(user_id, result)
        return _format_report(result, reconciliation, intent)

    async def _reconcile(
        self, user_id: UserId, result: ExtractionResult
    ) -> ReconciliationResult | None:
        """Compare the extracted lines with the user's records; ``None`` if that fails."""
        if not result.movements:
            return None
        lines = [_to_statement_line(m) for m in result.movements]
        try:
            return await self._reconciler.reconcile(user_id, lines)
        except _RECONCILE_FAILURES as e:
            logger.error(
                "Statement reconciliation failed; proposing without comparing",
                user_id=user_id,
                lines=len(lines),
                error=str(e),
            )
            return None


def _parse_extraction(raw: str) -> ExtractionResult:
    """Parse the model's JSON output, tolerating code fences and stray text."""
    text = raw.strip()
    if text.startswith("```"):
        # Drop a ```json ... ``` fence if the model added one.
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        text = text.removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        return ExtractionResult.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as e:
        raise ValueError(f"Unparseable extraction output: {e}") from e


def _resolve_movement_date(raw: str | None, today: date) -> str | None:
    """ISO date of ``raw`` with a misread year corrected; unparseable stays as is."""
    if not raw:
        return raw
    try:
        parsed = date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return raw
    return resolve_statement_date(parsed, today).isoformat()


def _with_resolved_dates(result: ExtractionResult, today: date) -> ExtractionResult:
    """Copy of ``result`` whose movement dates have a plausible year."""
    return result.model_copy(
        update={
            "movements": [
                m.model_copy(update={"date": _resolve_movement_date(m.date, today)})
                for m in result.movements
            ]
        }
    )


def _reclassify_card_payments(result: ExtractionResult) -> ExtractionResult:
    """Mark "Gracias por tu pago"-style INCOME lines of a credit statement as card payments.

    The model usually gets this right, but a payment received read as income would be
    proposed (and registered) as money earned. So an income line whose description has
    a card-payment keyword becomes ``card_payment`` when the document itself is a
    credit-card one (some movement is paid on credit or carries a card). The user's
    note is NOT evidence (a savings statement with "revisa si pagué la tarjeta" stays
    as is), and an expense is never rewritten.
    """
    if not _has_credit_context(result):
        return result
    card = next((m.card for m in result.movements if m.card), None)
    return result.model_copy(
        update={
            "movements": [
                m.model_copy(
                    update={
                        "transaction_type": StatementLineKind.CARD_PAYMENT,
                        "card": m.card or card,
                    }
                )
                if _is_card_payment_income(m)
                else m
                for m in result.movements
            ]
        }
    )


def _has_credit_context(result: ExtractionResult) -> bool:
    return any(m.payment_method == "credito" or m.card for m in result.movements)


def _is_card_payment_income(movement: ExtractedMovement) -> bool:
    text = normalize(movement.description)
    return movement.transaction_type == StatementLineKind.INCOME and any(
        keyword in text for keyword in CARD_PAYMENT_KEYWORDS
    )


def _to_statement_line(movement: ExtractedMovement) -> StatementLine:
    """The reconcilable form of an extracted movement (no/invalid date → undated)."""
    return StatementLine(
        description=movement.description,
        amount=movement.amount,
        date=_parse_date(movement.date),
        kind=_line_kind(movement),
        card=movement.card,
    )


def _parse_date(raw: str | None) -> date | None:
    """The movement's date, or ``None`` when absent/unparseable (never reconciled)."""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip()[:10])
    except ValueError:
        return None


def _line_kind(movement: ExtractedMovement) -> StatementLineKind:
    if movement.transaction_type == StatementLineKind.CARD_PAYMENT:
        return StatementLineKind.CARD_PAYMENT
    if movement.transaction_type == StatementLineKind.INCOME:
        return StatementLineKind.INCOME
    return StatementLineKind.EXPENSE


def _line_key(
    line: StatementLine,
) -> tuple[str, Decimal, date | None, StatementLineKind, str | None]:
    return (line.description, line.amount, line.date, line.kind, line.card)


def _missing_movements(
    movements: list[ExtractedMovement], reconciliation: ReconciliationResult | None
) -> list[ExtractedMovement]:
    """The movements the reconciliation found missing (all, when it did not run).

    Identical lines are interchangeable, so they are paired by value, one by one.
    """
    if reconciliation is None:
        return movements
    remaining = Counter(_line_key(line) for line in reconciliation.missing)

    def is_missing(movement: ExtractedMovement) -> bool:
        key = _line_key(_to_statement_line(movement))
        if remaining[key] <= 0:
            return False
        remaining[key] -= 1
        return True

    return [m for m in movements if is_missing(m)]


def _format_proposal(result: ExtractionResult) -> str:
    """Render the extracted movements as a proposal, none of them already registered."""
    lines = [_to_statement_line(m) for m in result.movements]
    return _format_report(result, ReconciliationResult(missing=lines))


def _format_report(
    result: ExtractionResult,
    reconciliation: ReconciliationResult | None = None,
    intent: IngestionIntent = IngestionIntent.REGISTER,
) -> str:
    """Render what was read, what is already registered and what is left to register.

    The registrable block (``PROPOSAL_HEADER`` … ``PROPOSAL_CONFIRM``) holds ONLY the
    missing lines; when none are missing it is omitted so a later "sí" registers
    nothing. ``reconciliation=None`` means the comparison did not run.
    """
    if not result.movements:
        base = "No encontré movimientos financieros en el archivo."
        if result.notes:
            base += f" {result.notes}"
        return base

    missing = _missing_movements(result.movements, reconciliation)
    matched = reconciliation.matched if reconciliation else []
    compared = reconciliation is not None
    if not compared and intent == IngestionIntent.VERIFY:
        # Nothing was compared, so there is nothing to report and nothing to register:
        # no marker, so a later "sí" cannot write unchecked (possibly duplicate) lines.
        read = len(result.movements)
        return f"Leí {read} {'movimiento' if read == 1 else 'movimientos'}. {_COULD_NOT_COMPARE_VERIFY}"

    lines = [_intro(len(result.movements), len(matched), intent, compared)]
    if not compared:
        lines.extend(["", _COULD_NOT_COMPARE_REGISTER])
    if matched:
        lines.append("")
        lines.extend(_format_matched(m) for m in matched)

    if not missing:
        return "\n".join([*lines, "", _ALL_REGISTERED])

    lines.extend(["", PROPOSAL_HEADER, ""])
    lines.extend(_format_movement(m) for m in missing[:MAX_LISTED_MOVEMENTS])

    hidden = len(missing) - MAX_LISTED_MOVEMENTS
    if hidden > 0:
        # Only listed movements can be registered on confirmation, so be explicit
        # that the rest need a separate image (never silently drop them on a "sí").
        lines.append(
            f"\n⚠️ Hay {hidden} movimiento(s) más que no alcancé a listar. Registraré "
            "los de arriba; envíame otra imagen con los que falten."
        )

    questions = _questions(result, missing)
    if questions:
        lines.append("")
        lines.append("Antes de registrar, cuéntame:")
        lines.extend(f"- {question}" for question in questions)

    lines.extend(
        [
            "",
            _CATEGORIZE_NOTE,
            f"{PROPOSAL_CONFIRM} Dime *sí* para guardarlos, o indícame qué corregir.",
        ]
    )
    return "\n".join(lines)


def _intro(total: int, registered: int, intent: IngestionIntent, compared: bool) -> str:
    """The opening sentence: how the document compares with the user's records."""
    noun = "movimiento" if total == 1 else "movimientos"
    if not compared:  # no comparison ran: claim nothing about what is registered
        return f"Leí {total} {noun}."
    if intent == IngestionIntent.VERIFY:
        return f"Revisé {total} {noun} contra tus registros: {registered} ya están registrados."
    if registered == total:  # nothing left to propose: don't say "propongo registrar"
        done = "ya está registrado" if total == 1 else f"los {total} ya están registrados"
        return f"Revisé {total} {noun}: {done}."
    if registered == 0:
        return f"Leí {total} {noun} y ninguno estaba registrado."
    return f"Ya tenías {registered} de {total} registrados; propongo registrar los restantes."


def _format_matched(matched: ReconciledLine) -> str:
    """Compact line for a movement the user already has registered."""
    line = matched.line
    if line.kind == StatementLineKind.CARD_PAYMENT:
        day = f"{matched.matched_date.day}-{_MONTHS_ES[matched.matched_date.month - 1]}"
        return f"💳 pago a tu {matched.matched_label} del {day} ya registrado"
    return f"✅ {line.description}: {_money(line.amount)} ({(line.date or matched.matched_date).isoformat()})"


def _questions(result: ExtractionResult, missing: list[ExtractedMovement]) -> list[str]:
    """At most one question: how it was paid, only if a missing expense has no method/card."""
    if not any(_lacks_payment_info(m) for m in missing):
        return []
    asked = next(
        (
            q
            for q in result.questions
            if _mentions(q, _PAYMENT_KEYWORDS) and not _mentions(q, _CATEGORY_MENTIONS)
        ),
        _PAYMENT_QUESTION,
    )
    return [asked][:MAX_QUESTIONS]


def _lacks_payment_info(movement: ExtractedMovement) -> bool:
    return (
        movement.transaction_type == StatementLineKind.EXPENSE
        and not movement.payment_method
        and not movement.card
    )


def _mentions(question: str, keywords: tuple[str, ...]) -> bool:
    text = normalize(question)
    return any(normalize(keyword) in text for keyword in keywords)


def _format_movement(movement: ExtractedMovement) -> str:
    """One-line summary of a movement for the proposal."""
    if movement.transaction_type == StatementLineKind.CARD_PAYMENT:
        return _format_card_payment(movement)
    sign = "ingreso" if movement.transaction_type == StatementLineKind.INCOME else "gasto"
    parts = [
        f"- {movement.description}: {_money(movement.amount)} ({sign}",
        f", {movement.category or _AUTO_CATEGORY}",
    ]
    if movement.date:
        parts.append(f", {movement.date}")
    if movement.payment_method:
        parts.append(f", {movement.payment_method}")
    if movement.card:
        parts.append(f", tarjeta {movement.card}")
    return "".join(parts) + ")"


def _format_card_payment(movement: ExtractedMovement) -> str:
    target = f"Pago a tarjeta {movement.card}" if movement.card else "Pago a tarjeta"
    when = f", {movement.date}" if movement.date else ""
    return f"- {target}: {_money(movement.amount)} (pago de tarjeta{when})"


def _money(value: Decimal) -> str:
    """Format an amount in Colombian style: dot thousands, no decimals ($200.000)."""
    return "$" + f"{value:,.0f}".replace(",", ".")
