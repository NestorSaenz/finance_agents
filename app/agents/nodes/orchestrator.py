"""Orchestrator agent node.

The orchestrator is the entry point for all user queries.
It interprets the user's intent and determines which agent should handle it.
"""

from app.agents.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)


async def orchestrator_node(state: AgentState) -> AgentState:
    """Process user input and determine intent and routing.

    Args:
        state: Current agent state with user message.

    Returns:
        Updated state with detected intent and next agent.
    """
    messages = state.get("messages", [])
    if not messages:
        logger.warning("Orchestrator received empty messages")
        return {
            **state,
            "detected_intent": "unknown",
            "next_agent": "response_generator",
        }

    user_message = messages[-1].content.lower()
    logger.info("Orchestrator processing message", message_length=len(user_message))

    # Intent detection logic
    # TODO: Replace with LLM-based intent classification
    intent, next_agent = _classify_intent(user_message)

    logger.info(
        "Intent classified",
        intent=intent,
        next_agent=next_agent,
    )

    return {
        **state,
        "detected_intent": intent,
        "next_agent": next_agent,
        "iteration_count": 0,
        "max_iterations": 10,
    }


def _classify_intent(message: str) -> tuple[str, str]:
    """Classify user intent based on message content.

    Args:
        message: Lowercase user message.

    Returns:
        Tuple of (intent, next_agent).
    """
    # Categorization intents
    if any(
        term in message
        for term in ["categoriza", "clasifica", "qué tipo", "categoría"]
    ):
        return "categorize", "categorizer"

    # Analysis intents
    if any(
        term in message
        for term in [
            "cuánto gasté",
            "análisis",
            "analiza",
            "gastos",
            "resumen",
            "patrones",
        ]
    ):
        return "analyze", "analyst"

    # Planning intents
    if any(
        term in message
        for term in ["plan", "ahorro", "meta", "objetivo", "estrategia", "ahorrar"]
    ):
        return "plan", "planner"

    # Recommendation intents
    if any(
        term in message
        for term in ["recomienda", "sugerencia", "consejo", "optimizar", "mejorar"]
    ):
        return "recommend", "recommender"

    # Action intents (registering transactions)
    if any(term in message for term in ["registra", "agrega", "añade", "gastE"]):
        return "register", "categorizer"

    # Default to analyst for general queries
    return "query", "analyst"
