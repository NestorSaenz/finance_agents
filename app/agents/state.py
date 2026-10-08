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
    timezone: str  # user's IANA timezone, for resolving relative dates in their local day
    conversation_id: str  # chat conversation this turn belongs to ('' when unknown)
    turn_id: str  # unique id of THIS request; separates 'propose' from a later 'confirm'

    # Routing / results.
    detected_intent: str
    category_suggestion: str | None  # set by the categorizer, phrased by response_generator
    next_agent: str
    should_respond: bool
    # Set by a node that could not complete the turn (fallback answer): the route then
    # drops any proposal made in it, since the user never saw it.
    turn_failed: bool


def build_initial_state(
    message: str,
    user_id: str,
    history: list[BaseMessage] | None = None,
    user_context: str = "",
    timezone: str = "",
    conversation_id: str = "",
    turn_id: str = "",
) -> AgentState:
    """Build a fresh :class:`AgentState` for a new user turn.

    Args:
        message: The user's new message.
        user_id: Identifier of the user owning the conversation.
        history: Prior conversation messages (oldest first) for multi-turn context.
        user_context: The user's long-term knowledge facts, for personalization.
        timezone: The user's IANA timezone, used to resolve "today" in their local day.
        conversation_id: The chat conversation id (scopes pending confirmations).
        turn_id: Unique id of this request; a pending proposal can only be confirmed
            from a different turn.

    Returns:
        A fully populated initial state.
    """
    return AgentState(
        messages=[*(history or []), HumanMessage(content=message)],
        user_id=user_id,
        user_context=user_context,
        timezone=timezone,
        conversation_id=conversation_id,
        turn_id=turn_id,
        detected_intent="unknown",
        category_suggestion=None,
        next_agent="",
        should_respond=False,
        turn_failed=False,
    )
