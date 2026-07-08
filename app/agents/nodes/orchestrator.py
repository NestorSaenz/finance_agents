"""Orchestrator agent node.

The orchestrator is the entry point for all user queries.
It uses an LLM-based classifier to interpret the user's intent
and determine which agent should handle the request.
"""

from app.agents.context import prior_context
from app.agents.nodes.classifier import classify_query
from app.agents.state import AgentState
from app.agents.types import AgentName
from app.core.logging import get_logger
from app.shared.interfaces.llm import LLMInterface

# Prior messages given to the classifier to resolve references ("eso", "el anterior").
CLASSIFIER_CONTEXT_WINDOW = 4

logger = get_logger(__name__)


async def orchestrator_node(state: AgentState, llm: LLMInterface) -> dict[str, object]:
    """Process user input and determine intent and routing using LLM.

    Args:
        state: Current agent state with user message.
        llm: LLM client for classification.

    Returns:
        Updated state with detected intent, complexity and next agent.
    """
    messages = state.get("messages", [])
    if not messages:
        logger.warning("Orchestrator received empty messages")
        return {
            "detected_intent": "unknown",
            "next_agent": AgentName.RESPONSE_GENERATOR.value,
        }

    user_message = str(messages[-1].content)
    logger.info("Orchestrator processing message", message_length=len(user_message))

    # LLM-based intent classification (with recent context for reference resolution).
    classification = await classify_query(
        user_message, llm, context=prior_context(state, limit=CLASSIFIER_CONTEXT_WINDOW)
    )

    logger.info(
        "Query classified",
        intent=classification.intent,
        next_agent=classification.next_agent,
    )

    return {
        "detected_intent": classification.intent,
        "next_agent": classification.next_agent.value,
    }
