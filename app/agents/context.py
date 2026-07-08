"""Conversation-context helpers shared by the agent nodes.

Centralizes converting the graph state's LangChain messages into the LLM
``Message`` format, so each node builds context the same way. Nodes request the
window they need: the classifier only needs a couple of turns to disambiguate
references, while the tool agent and response generator use the full recent
history.
"""

from langchain_core.messages import AIMessage

from app.agents.state import AgentState
from app.shared.interfaces.llm import Message, MessageRole


def conversation_messages(state: AgentState, limit: int | None = None) -> list[Message]:
    """Convert the state's messages (incl. the current one) to LLM messages.

    Args:
        state: The agent state.
        limit: If given, keep only the last ``limit`` messages.

    Returns:
        Messages oldest-first, with empty ones skipped.
    """
    messages = list(state.get("messages", []))
    if limit is not None:
        messages = messages[-limit:]
    return _convert(messages)


def prior_context(state: AgentState, limit: int | None = None) -> list[Message]:
    """Return the conversation BEFORE the current message (for context).

    Excludes the last message (the user's new one, which the calling prompt
    already references), keeping only the last ``limit`` prior messages.
    """
    messages = list(state.get("messages", []))
    prior = messages[:-1]  # drop the current message
    if limit is not None:
        prior = prior[-limit:]
    return _convert(prior)


def user_context_block(state: AgentState) -> str:
    """Return a prompt block with the user's long-term facts, or "" if none."""
    context = state.get("user_context", "")
    if not context:
        return ""
    return f"\n\n## Lo que sabemos del usuario (memoria):\n{context}\n"


def _convert(messages: list) -> list[Message]:
    result: list[Message] = []
    for message in messages:
        content = getattr(message, "content", "")
        if not content:
            continue
        role = MessageRole.ASSISTANT if isinstance(message, AIMessage) else MessageRole.USER
        result.append(Message(role=role, content=str(content)))
    return result
