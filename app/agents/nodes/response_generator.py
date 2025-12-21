"""Response generator agent node.

The response generator synthesizes the final response
from all intermediate results into a coherent, user-friendly message.
"""

from langchain_core.messages import AIMessage

from app.agents.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)


async def response_generator_node(state: AgentState) -> AgentState:
    """Generate the final response for the user.

    Args:
        state: Current agent state with all intermediate results.

    Returns:
        Updated state with final response message.
    """
    detected_intent = state.get("detected_intent", "unknown")
    logger.info("Response generator processing", intent=detected_intent)

    # Collect results from different agents
    category_suggestion = state.get("category_suggestion")
    analysis_results = state.get("analysis_results")
    recommendations = state.get("recommendations", [])
    execution_history = state.get("execution_history", [])

    # TODO: Replace with LLM-based response generation
    # For now, build a simple response based on available data

    response_parts = []

    if category_suggestion:
        response_parts.append(
            f"He categorizado tu transacción como: {category_suggestion}"
        )

    if analysis_results:
        response_parts.append("He analizado tus finanzas y encontré algunos insights.")

    if recommendations:
        response_parts.append("Mis recomendaciones:")
        for rec in recommendations:
            response_parts.append(f"  • {rec}")

    if execution_history:
        response_parts.append(
            f"He ejecutado {len(execution_history)} pasos para analizar tu solicitud."
        )

    if not response_parts:
        response_parts.append(
            "Lo siento, no pude procesar tu solicitud. "
            "¿Podrías reformularla de otra manera?"
        )

    final_response = "\n".join(response_parts)
    logger.info("Response generated", response_length=len(final_response))

    # Add the response to messages
    messages = state.get("messages", [])
    messages.append(AIMessage(content=final_response))

    return {
        **state,
        "messages": messages,
        "should_respond": False,  # Response has been generated
    }
