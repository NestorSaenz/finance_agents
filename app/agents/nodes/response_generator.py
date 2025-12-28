"""Response generator agent node.

The response generator synthesizes the final response from all intermediate
results into a coherent, user-friendly message using LLM.
"""

from langchain_core.messages import AIMessage

from app.agents.nodes.response_generator_constants import (
    ANALYSIS_TEMPLATE,
    CATEGORIZATION_TEMPLATE,
    COMPLEX_RESPONSE_TEMPLATE,
    GENERAL_TEMPLATE,
    PLANNING_TEMPLATE,
    RECOMMENDATION_TEMPLATE,
    RESPONSE_SYSTEM_PROMPT,
)
from app.agents.state import AgentState
from app.core.logging import get_logger
from app.shared.interfaces.llm import LLMConfig, LLMInterface, Message, MessageRole

logger = get_logger(__name__)


async def response_generator_node(
    state: AgentState,
    llm: LLMInterface,
) -> AgentState:
    """Generate the final response for the user using LLM.

    Takes all intermediate results from other agents and synthesizes
    a natural, helpful response in Spanish.

    Args:
        state: Current agent state with all intermediate results.
        llm: LLM client for generating the response.

    Returns:
        Updated state with final response message.
    """
    detected_intent = state.get("detected_intent", "unknown")
    messages = state.get("messages", [])

    logger.info("Response generator processing", intent=detected_intent)

    # Get the original user message
    user_message = _get_last_user_message(messages)

    # Build the prompt based on intent and available data
    prompt = _build_prompt(state, user_message)

    # Generate response with LLM
    try:
        response_text = await _generate_response(llm, prompt)
    except Exception as e:
        logger.error("LLM generation failed", error=str(e))
        response_text = _build_fallback_response(state)

    logger.info("Response generated", response_length=len(response_text))

    # Add the response to messages
    messages.append(AIMessage(content=response_text))

    return {
        **state,
        "messages": messages,
        "should_respond": False,  # Response has been generated
    }


def _get_last_user_message(messages: list) -> str:
    """Extract the last user message from the conversation."""
    for message in reversed(messages):
        if hasattr(message, "type") and message.type == "human":
            return message.content
        if hasattr(message, "role") and message.role == "user":
            return message.content
    return ""


def _build_prompt(state: AgentState, user_message: str) -> str:
    """Build the prompt based on intent and available data.

    Args:
        state: Current agent state.
        user_message: Original user message.

    Returns:
        Formatted prompt for LLM.
    """
    detected_intent = state.get("detected_intent", "unknown")
    category_suggestion = state.get("category_suggestion")
    analysis_results = state.get("analysis_results")
    recommendations = state.get("recommendations", [])
    execution_history = state.get("execution_history", [])

    # Check if this was a complex query with execution history
    if execution_history:
        return _build_complex_prompt(state, user_message)

    # Build prompt based on intent
    if detected_intent == "categorize" and category_suggestion:
        return _build_categorization_prompt(state, user_message)

    if detected_intent == "analyze" and analysis_results:
        return _build_analysis_prompt(state, user_message)

    if detected_intent == "recommend" and recommendations:
        return _build_recommendation_prompt(state, user_message)

    if detected_intent == "plan":
        return _build_planning_prompt(state, user_message)

    # Default: general template
    return _build_general_prompt(state, user_message)


def _build_categorization_prompt(state: AgentState, user_message: str) -> str:
    """Build prompt for categorization response."""
    category = state.get("category_suggestion", "otros")
    # Note: confidence would come from CategorySuggestion model in full implementation
    confidence = 0.85  # Placeholder

    return CATEGORIZATION_TEMPLATE.format(
        category=category,
        confidence=confidence,
        alternatives="ninguna",
        user_message=user_message,
    )


def _build_analysis_prompt(state: AgentState, user_message: str) -> str:
    """Build prompt for analysis response."""
    results = state.get("analysis_results", {})

    total_income = results.get("total_income", 0)
    total_expenses = results.get("total_expenses", 0)
    balance = total_income - total_expenses
    by_category = results.get("by_category", {})
    patterns = results.get("patterns", [])
    insights = results.get("insights", [])

    # Format category breakdown
    if by_category:
        category_str = "\n".join(
            f"  • {cat}: ${amount:,.2f}" for cat, amount in by_category.items()
        )
    else:
        category_str = "  No hay datos de categorías disponibles"

    # Format patterns
    patterns_str = "\n".join(f"  • {p}" for p in patterns) if patterns else "  Ninguno detectado"

    # Format insights
    insights_str = "\n".join(f"  • {i}" for i in insights) if insights else "  Sin insights adicionales"

    return ANALYSIS_TEMPLATE.format(
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance,
        by_category=category_str,
        patterns=patterns_str,
        insights=insights_str,
        user_message=user_message,
    )


def _build_recommendation_prompt(state: AgentState, user_message: str) -> str:
    """Build prompt for recommendation response."""
    recommendations = state.get("recommendations", [])
    active_goals = state.get("active_goals", [])

    # Format recommendations
    if recommendations:
        recs_str = "\n".join(f"  {i+1}. {rec}" for i, rec in enumerate(recommendations))
    else:
        recs_str = "  No hay recomendaciones disponibles"

    # Format goals
    goals_str = str(len(active_goals)) if active_goals else "0"

    return RECOMMENDATION_TEMPLATE.format(
        recommendations=recs_str,
        monthly_income=0,  # Would come from user profile
        monthly_expenses=0,
        active_goals=goals_str,
        user_message=user_message,
    )


def _build_planning_prompt(state: AgentState, user_message: str) -> str:
    """Build prompt for planning response."""
    # Placeholder - would use SavingsPlan model data
    return PLANNING_TEMPLATE.format(
        goal_name="Meta de ahorro",
        target_amount=0,
        current_amount=0,
        monthly_contribution=0,
        estimated_completion="Por determinar",
        recommendations="  Sin recomendaciones específicas aún",
        user_message=user_message,
    )


def _build_complex_prompt(state: AgentState, user_message: str) -> str:
    """Build prompt for complex multi-step response."""
    execution_history = state.get("execution_history", [])

    # Format execution history
    history_str = "\n".join(
        f"  {i+1}. {step.get('description', 'Paso ejecutado')}: {step.get('status', 'completado')}"
        for i, step in enumerate(execution_history)
    )

    # Collect all results
    results = {
        "category": state.get("category_suggestion"),
        "analysis": state.get("analysis_results"),
        "recommendations": state.get("recommendations"),
    }
    results_str = "\n".join(
        f"  • {k}: {'Disponible' if v else 'No disponible'}"
        for k, v in results.items()
    )

    return COMPLEX_RESPONSE_TEMPLATE.format(
        execution_history=history_str,
        results=results_str,
        user_message=user_message,
    )


def _build_general_prompt(state: AgentState, user_message: str) -> str:
    """Build prompt for general/unknown intent."""
    return GENERAL_TEMPLATE.format(
        intent=state.get("detected_intent", "unknown"),
        user_message=user_message,
        category_suggestion=state.get("category_suggestion", "No"),
        has_analysis="Sí" if state.get("analysis_results") else "No",
        recommendations_count=len(state.get("recommendations", [])),
    )


async def _generate_response(llm: LLMInterface, prompt: str) -> str:
    """Generate response using LLM.

    Args:
        llm: LLM client.
        prompt: Formatted prompt.

    Returns:
        Generated response text.
    """
    config = LLMConfig(
        temperature=0.7,  # Some creativity for natural responses
        max_tokens=500,  # Reasonable length for responses
    )

    messages = [
        Message(role=MessageRole.SYSTEM, content=RESPONSE_SYSTEM_PROMPT),
        Message(role=MessageRole.USER, content=prompt),
    ]

    response = await llm.generate(messages=messages, config=config)
    return response.content.strip()


def _build_fallback_response(state: AgentState) -> str:
    """Build a fallback response when LLM fails.

    Args:
        state: Current agent state.

    Returns:
        Simple fallback response.
    """
    category = state.get("category_suggestion")
    analysis = state.get("analysis_results")
    recommendations = state.get("recommendations", [])

    parts = []

    if category:
        parts.append(f"He categorizado tu transacción como: **{category}**")

    if analysis:
        parts.append("He analizado tus finanzas. Revisa el resumen en tu dashboard.")

    if recommendations:
        parts.append("Tengo algunas recomendaciones para ti:")
        for rec in recommendations[:3]:
            parts.append(f"  • {rec}")

    if not parts:
        parts.append(
            "Lo siento, no pude procesar tu solicitud completamente. "
            "¿Podrías intentar de nuevo o reformular tu pregunta?"
        )

    return "\n\n".join(parts)
