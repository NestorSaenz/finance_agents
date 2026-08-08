"""Image ingestion: extract financial movements from a photo/screenshot.

The user attaches an image of their spreadsheet (or a receipt). A vision model
extracts the movements as structured rows; we turn that into a Spanish proposal
that lists what was read and asks the user to confirm (or fix ambiguities) BEFORE
anything is registered. On the user's confirmation, the normal tool agent reads
the proposal from the conversation history and registers each movement — so the
extracted amounts are shown for review first, never written blindly.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Final

from pydantic import BaseModel, ValidationError

from app.core.logging import get_logger
from app.shared.interfaces.llm import (
    ImagePart,
    LLMConfig,
    LLMInterface,
    Message,
    MessageRole,
)

logger = get_logger(__name__)

EXTRACTION_TEMPERATURE: Final[float] = 0.0
EXTRACTION_MAX_TOKENS: Final[int] = 2048
# Cap listed rows so the confirmable proposal stays complete: only listed rows can
# be registered on confirmation, so this must be generous (a single image rarely
# holds more legible rows). If exceeded, the user is told the rest need another image.
MAX_LISTED_MOVEMENTS: Final[int] = 200

# Marker phrases shared with the tool agent's prompt: the proposal starts with the
# header and ends with the confirm question, which is how a "sí" is recognized as a
# batch registration. Keep these as the single source of truth for both sides.
PROPOSAL_HEADER: Final[str] = "Leí esto de tu archivo:"
PROPOSAL_CONFIRM: Final[str] = "¿Los registro tal cual?"

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

# Asked when an expense has no category and the model didn't already ask: better to
# confirm than to silently auto-categorize an ambiguous charge (e.g. a store name).
_CATEGORY_QUESTION: Final[str] = (
    "¿En qué categoría lo clasifico? (por ejemplo: gimnasio, mercado, servicios…)"
)
_CATEGORY_KEYWORDS: Final[tuple[str, ...]] = ("categoría", "categoria", "clasifico", "clasificar")

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
    '      "transaction_type": "expense" | "income",\n'
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
    "- Si NO puedes deducir la categoría del gasto con confianza (p. ej. solo hay un "
    "nombre de comercio ambiguo), deja category en null y AÑADE en 'questions' una "
    "pregunta para que el usuario la indique. NO inventes una categoría.\n"
    "- Si una celda es ambigua o dudosa, incluye tu mejor interpretación y AÑADE "
    "una pregunta clara en 'questions'.\n"
    "- MÉTODO DE PAGO: una factura casi nunca dice cómo se pagó. Si el documento no "
    "indica claramente 'efectivo' o 'crédito', deja payment_method en null y AÑADE en "
    "'questions' una pregunta para saber cómo lo pagó el usuario.\n"
    "- NOTA DEL USUARIO: si la nota indica cómo pagó o con qué tarjeta (p. ej. 'son de "
    "mi tarjeta Nu', 'todo a crédito'), aplícalo a TODOS los movimientos: pon "
    "payment_method='credito' y card con el nombre de la tarjeta. Así NO vuelvas a "
    "preguntar el método ni la tarjeta.\n"
    "- Si no hay fecha, usa null (se asumirá la fecha de hoy).\n"
    "- Si el documento no contiene movimientos financieros, devuelve movements vacío."
)

_USER_PROMPT: Final[str] = (
    "Extrae los movimientos financieros de este documento y devuélvelos en el JSON pedido."
)


class ExtractedMovement(BaseModel):
    """A single movement read from the image (pre-registration)."""

    description: str
    amount: Decimal
    transaction_type: str = "expense"
    date: str | None = None
    category: str | None = None
    payment_method: str | None = None
    card: str | None = None  # credit card name, if the user's note said one


class ExtractionResult(BaseModel):
    """The structured result of reading an image."""

    movements: list[ExtractedMovement] = []
    questions: list[str] = []
    notes: str | None = None


class ImageIngestionServiceABC(ABC):
    """Contract for reading an image and proposing the movements to register."""

    @abstractmethod
    async def propose(
        self, image: bytes, mime_type: str, user_context: str = "", user_note: str = ""
    ) -> str:
        """Extract movements from ``image`` and return a Spanish proposal to confirm."""


class ImageIngestionService(ImageIngestionServiceABC):
    """Reads an image with a vision LLM and proposes the movements to register."""

    def __init__(self, llm: LLMInterface) -> None:
        self._llm = llm

    async def propose(
        self, image: bytes, mime_type: str, user_context: str = "", user_note: str = ""
    ) -> str:
        """Extract movements from ``image`` and return a Spanish proposal to confirm."""
        system_content = _SYSTEM_PROMPT
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

        logger.info("Image ingestion parsed", movements=len(result.movements))
        return _format_proposal(result)


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


def _format_proposal(result: ExtractionResult) -> str:
    """Render the extracted movements as a Spanish proposal awaiting confirmation."""
    if not result.movements:
        base = "No encontré movimientos financieros en el archivo."
        if result.notes:
            base += f" {result.notes}"
        return base

    lines = [PROPOSAL_HEADER, ""]
    lines.extend(_format_movement(m) for m in result.movements[:MAX_LISTED_MOVEMENTS])

    hidden = len(result.movements) - MAX_LISTED_MOVEMENTS
    if hidden > 0:
        # Only listed movements can be registered on confirmation, so be explicit
        # that the rest need a separate image (never silently drop them on a "sí").
        lines.append(
            f"\n⚠️ Hay {hidden} movimiento(s) más que no alcancé a listar. Registraré "
            "los de arriba; envíame otra imagen con los que falten."
        )

    questions = list(result.questions)
    if _needs_category_question(result):
        questions.append(_CATEGORY_QUESTION)
    if _needs_payment_question(result):
        questions.append(_PAYMENT_QUESTION)

    if questions:
        lines.append("")
        lines.append("Antes de registrar, cuéntame:")
        lines.extend(f"- {question}" for question in questions)

    lines.append("")
    lines.append(f"{PROPOSAL_CONFIRM} Dime *sí* para guardarlos, o indícame qué corregir.")
    return "\n".join(lines)


def _needs_category_question(result: ExtractionResult) -> bool:
    """True when a listed expense has no category and no question asks for it."""
    missing = any(
        movement.transaction_type != "income" and not movement.category
        for movement in result.movements[:MAX_LISTED_MOVEMENTS]
    )
    if not missing:
        return False
    already_asked = any(
        keyword in question.lower()
        for question in result.questions
        for keyword in _CATEGORY_KEYWORDS
    )
    return not already_asked


def _needs_payment_question(result: ExtractionResult) -> bool:
    """True when a listed expense lacks a payment method and no question asks for it."""
    missing = any(
        movement.transaction_type != "income" and not movement.payment_method
        for movement in result.movements[:MAX_LISTED_MOVEMENTS]
    )
    if not missing:
        return False
    already_asked = any(
        keyword in question.lower()
        for question in result.questions
        for keyword in _PAYMENT_KEYWORDS
    )
    return not already_asked


def _format_movement(movement: ExtractedMovement) -> str:
    """One-line summary of a movement for the proposal."""
    sign = "ingreso" if movement.transaction_type == "income" else "gasto"
    parts = [f"- {movement.description}: {_money(movement.amount)} ({sign}"]
    if movement.category:
        parts.append(f", {movement.category}")
    if movement.date:
        parts.append(f", {movement.date}")
    if movement.payment_method:
        parts.append(f", {movement.payment_method}")
    if movement.card:
        parts.append(f", tarjeta {movement.card}")
    return "".join(parts) + ")"


def _money(value: Decimal) -> str:
    """Format an amount in Colombian style: dot thousands, no decimals ($200.000)."""
    return "$" + f"{value:,.0f}".replace(",", ".")
