"""The response generator has no tools, so it must never claim a completed write."""

from app.agents.nodes.action_claims import FALSE_CLAIM_REPLY
from app.agents.nodes.response_generator import response_generator_node
from app.agents.state import build_initial_state
from tests.fakes import FakeLLM


async def test_claimed_write_is_replaced() -> None:
    state = build_initial_state(message="sí", user_id="u1")

    result = await response_generator_node(state, FakeLLM("¡Listo! Registré tus gastos."))

    assert result["messages"][-1].content == FALSE_CLAIM_REPLY


async def test_honest_reply_is_kept() -> None:
    state = build_initial_state(message="hola", user_id="u1")

    result = await response_generator_node(state, FakeLLM("¡Hola! ¿En qué te ayudo?"))

    assert result["messages"][-1].content == "¡Hola! ¿En qué te ayudo?"
