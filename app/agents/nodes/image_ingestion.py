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
    '      "payment_method": "efectivo" | "credito" | null\n'
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
    "- Si una celda es ambigua o dudosa, incluye tu mejor interpretación y AÑADE "
    "una pregunta clara en 'questions'.\n"
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


class ExtractionResult(BaseModel):
    """The structured result of reading an image."""

    movements: list[ExtractedMovement] = []
    questions: list[str] = []
    notes: str | None = None


class ImageIngestionServiceABC(ABC):
    """Contract for reading an image and proposing the movements to register."""

    @abstractmethod
    async def propose(self, image: bytes, mime_type: str, user_context: str = "") -> str:
        """Extract movements from ``image`` and return a Spanish proposal to confirm."""


class ImageIngestionService(ImageIngestionServiceABC):
    """Reads an image with a vision LLM and proposes the movements to register."""

    def __init__(self, llm: LLMInterface) -> None:
        self._llm = llm

    async def propose(self, image: bytes, mime_type: str, user_context: str = "") -> str:
        """Extract movements from ``image`` and return a Spanish proposal to confirm."""
        system_content = _SYSTEM_PROMPT
        if user_context:
            system_content = f"{system_content}\n\nContexto del usuario:\n{user_context}"

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_content),
            Message(
                role=MessageRole.USER,
                content=_USER_PROMPT,
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

    if result.questions:
        lines.append("")
        lines.append("Antes de registrar, cuéntame:")
        lines.extend(f"- {question}" for question in result.questions)

    lines.append("")
    lines.append(f"{PROPOSAL_CONFIRM} Dime *sí* para guardarlos, o indícame qué corregir.")
    return "\n".join(lines)


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
    return "".join(parts) + ")"


def _money(value: Decimal) -> str:
    """Format an amount in Colombian style: dot thousands, no decimals ($200.000)."""
    return "$" + f"{value:,.0f}".replace(",", ".")
