"""Unit tests for the image ingestion service (vision LLM mocked)."""

import pytest

from app.agents.nodes.image_ingestion import ImageIngestionService
from tests.fakes import FakeLLM

pytestmark = pytest.mark.asyncio

_VALID_JSON = """
{
  "movements": [
    {"description": "Supermercado", "amount": 200000, "transaction_type": "expense",
     "date": "2026-07-01", "category": "alimentacion", "payment_method": "efectivo"},
    {"description": "Poda jardín", "amount": 50000, "transaction_type": "expense",
     "date": null, "category": "jardinería", "payment_method": null}
  ],
  "questions": ["¿'M' significa mercado?"],
  "notes": null
}
"""


async def test_propose_lists_movements_and_asks_confirmation() -> None:
    service = ImageIngestionService(FakeLLM(_VALID_JSON))

    proposal = await service.propose(b"\x89PNG-bytes", "image/png")

    assert "Supermercado" in proposal
    assert "$200.000" in proposal  # Colombian format: dot thousands separator
    assert "jardinería" in proposal  # custom category preserved in the proposal
    assert "¿'M' significa mercado?" in proposal  # ambiguity surfaced
    assert "¿Los registro tal cual?" in proposal  # asks before saving


async def test_propose_sends_image_to_the_llm() -> None:
    fake = FakeLLM(_VALID_JSON)
    service = ImageIngestionService(fake)

    await service.propose(b"rawbytes", "image/jpeg", user_context="El usuario se llama Ana.")

    # The user message carries the image part; the system prompt carries the context.
    user_message = fake.calls[0][-1]
    assert user_message.images is not None
    assert user_message.images[0].data == b"rawbytes"
    assert user_message.images[0].mime_type == "image/jpeg"
    assert any("Ana" in m.content for m in fake.calls[0])


async def test_propose_handles_no_movements() -> None:
    service = ImageIngestionService(FakeLLM('{"movements": [], "questions": [], "notes": null}'))

    proposal = await service.propose(b"x", "image/png")

    assert "No encontré movimientos" in proposal


async def test_propose_tolerates_code_fenced_json() -> None:
    fenced = "```json\n" + _VALID_JSON + "\n```"
    service = ImageIngestionService(FakeLLM(fenced))

    proposal = await service.propose(b"x", "image/png")

    assert "Supermercado" in proposal


async def test_propose_degrades_on_unparseable_output() -> None:
    service = ImageIngestionService(FakeLLM("lo siento, no es json"))

    proposal = await service.propose(b"x", "image/png")

    assert "No pude leer la imagen" in proposal
