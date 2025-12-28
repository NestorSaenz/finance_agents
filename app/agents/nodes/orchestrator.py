"""Orchestrator agent node.

The orchestrator is the entry point for all user queries.
It uses an LLM-based classifier to interpret the user's intent
and determine which agent should handle the request.
"""

from app.agents.constants import DEFAULT_MAX_ITERATIONS
from app.agents.nodes.classifier import classify_query
from app.agents.state import AgentState
from app.agents.types import AgentName
from app.core.logging import get_logger
from app.shared.interfaces.llm import LLMInterface

logger = get_logger(__name__)


async def orchestrator_node(state: AgentState, llm: LLMInterface) -> AgentState:
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
            **state,
            "detected_intent": "unknown",
            "query_complexity": "simple",
            "next_agent": AgentName.RESPONSE_GENERATOR.value,
        }

    user_message = messages[-1].content
    logger.info("Orchestrator processing message", message_length=len(user_message))

    # LLM-based intent and complexity classification
    classification = await classify_query(user_message, llm)

    logger.info(
        "Query classified",
        intent=classification.intent,
        complexity=classification.complexity,
        confidence=classification.confidence,
        next_agent=classification.next_agent,
    )

    return {
        **state,
        "detected_intent": classification.intent,
        "query_complexity": classification.complexity,
        "next_agent": classification.next_agent.value if hasattr(classification.next_agent, 'value') else classification.next_agent,
        "iteration_count": 0,
        "max_iterations": DEFAULT_MAX_ITERATIONS,
    }
