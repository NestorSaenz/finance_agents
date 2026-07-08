"""Refusal node: politely declines out-of-scope (non-finance) requests.

Reached when the classifier tags a message as ``off_topic``. It returns a fixed
message with NO LLM call, so off-topic traffic is rejected at the gate — this
both keeps the assistant on-scope and prevents wasted token spend on requests
we don't want to serve.
"""

from langchain_core.messages import AIMessage

from app.agents.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)

REFUSAL_MESSAGE = (
    "Soy Safi y solo puedo ayudarte con tus finanzas personales: "
    "registrar y consultar gastos e ingresos, categorizar transacciones, "
    "analizar tus movimientos, y crear planes de ahorro. 😊\n\n"
    "¿En qué te gustaría que te ayude sobre tus finanzas?"
)


async def refusal_node(state: AgentState) -> dict[str, object]:
    """Return a fixed on-scope decline without calling any LLM.

    Args:
        state: Current agent state (used only to append the reply).

    Returns:
        Updated state with the canned refusal message.
    """
    logger.info("Declining out-of-scope request", user_id=state.get("user_id"))
    # Return only the delta: the add_messages reducer appends the new message.
    return {"messages": [AIMessage(content=REFUSAL_MESSAGE)], "should_respond": False}
