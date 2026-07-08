"""Response generator node.

Phrases the final user-facing reply for the two intents that reach it:
``categorize`` (after the categorizer) and ``unknown``/general (greetings,
vague messages). All data-driven intents are handled by the tool agent, which
writes its own answer, so this node no longer synthesizes analysis/plans.
"""

from langchain_core.messages import AIMessage

from app.agents.context import prior_context, user_context_block
from app.agents.nodes.response_generator_constants import (
    CATEGORIZATION_TEMPLATE,
    GENERAL_TEMPLATE,
    RESPONSE_SYSTEM_PROMPT,
)
from app.agents.state import AgentState
from app.core.logging import get_logger
from app.shared.interfaces.llm import LLMConfig, LLMInterface, Message, MessageRole

# Prior messages given to the response generator for coherent, contextual replies.
RESPONSE_CONTEXT_WINDOW = 8

logger = get_logger(__name__)


async def response_generator_node(
    state: AgentState,
    llm: LLMInterface,
) -> dict[str, object]:
    """Generate the final response for the user using the LLM.

    Args:
        state: Current agent state.
        llm: LLM client for generating the response.

    Returns:
        State delta with the final assistant message appended.
    """
    detected_intent = state.get("detected_intent", "unknown")
    logger.info("Response generator processing", intent=detected_intent)

    user_message = _get_last_user_message(state.get("messages", []))
    prompt = _build_prompt(state, user_message)

    # Recent conversation for coherence + the user's long-term facts for personalization.
    history = prior_context(state, limit=RESPONSE_CONTEXT_WINDOW)
    system_prompt = RESPONSE_SYSTEM_PROMPT + user_context_block(state)
    try:
        response_text = await _generate_response(llm, prompt, history, system_prompt)
    except Exception as e:  # noqa: BLE001 - LLM boundary: degrade gracefully.
        logger.error("LLM generation failed", error=str(e))
        response_text = _build_fallback_response(state)

    logger.info("Response generated", response_length=len(response_text))
    return {"messages": [AIMessage(content=response_text)], "should_respond": False}


def _get_last_user_message(messages: list) -> str:
    """Extract the last human message from the conversation."""
    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            return str(message.content)
    return ""


def _build_prompt(state: AgentState, user_message: str) -> str:
    """Build the prompt for the reachable intents (categorize / general)."""
    if state.get("detected_intent") == "categorize" and state.get("category_suggestion"):
        return CATEGORIZATION_TEMPLATE.format(
            category=state.get("category_suggestion", "otros"),
            user_message=user_message,
        )
    return GENERAL_TEMPLATE.format(
        intent=state.get("detected_intent", "unknown"),
        user_message=user_message,
    )


async def _generate_response(
    llm: LLMInterface,
    prompt: str,
    history: list[Message],
    system_prompt: str,
) -> str:
    """Generate the response using the LLM (recent history + memory in context)."""
    config = LLMConfig(temperature=0.7, max_tokens=500)
    messages = [
        Message(role=MessageRole.SYSTEM, content=system_prompt),
        *history,
        Message(role=MessageRole.USER, content=prompt),
    ]
    response = await llm.generate(messages=messages, config=config)
    return response.content.strip()


def _build_fallback_response(state: AgentState) -> str:
    """Deterministic fallback when the LLM call fails."""
    category = state.get("category_suggestion")
    if category:
        return f"He categorizado tu transacción como: **{category}**."
    return (
        "Lo siento, no pude procesar tu solicitud completamente. "
        "¿Podrías intentarlo de nuevo o reformular tu pregunta?"
    )
