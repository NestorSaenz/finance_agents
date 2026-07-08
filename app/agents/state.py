"""Agent state for the FinanceGPT graph."""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Shared state flowing through the graph nodes.

    Kept intentionally small: the orchestrator classifies intent and routes to a
    single terminal node, so there is no plan/execution state to carry.
    """

    # Conversation (append-only via the add_messages reducer).
    messages: Annotated[list[BaseMessage], add_messages]

    # Auth + long-term memory.
    user_id: str
    user_context: str  # durable facts about the user (Memory Agent), for personalization

    # Routing / results.
    detected_intent: str
    category_suggestion: str | None  # set by the categorizer, phrased by response_generator
    next_agent: str
    should_respond: bool


def build_initial_state(
    message: str,
    user_id: str,
    history: list[BaseMessage] | None = None,
    user_context: str = "",
) -> AgentState:
    """Build a fresh :class:`AgentState` for a new user turn.

    Args:
        message: The user's new message.
        user_id: Identifier of the user owning the conversation.
        history: Prior conversation messages (oldest first) for multi-turn context.
        user_context: The user's long-term knowledge facts, for personalization.

    Returns:
        A fully populated initial state.
    """
    return AgentState(
        messages=[*(history or []), HumanMessage(content=message)],
        user_id=user_id,
        user_context=user_context,
        detected_intent="unknown",
        category_suggestion=None,
        next_agent="",
        should_respond=False,
    )
