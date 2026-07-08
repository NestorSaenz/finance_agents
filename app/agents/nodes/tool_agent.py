"""Tool-calling agent node.

Handles actionable intents (register a transaction, query transactions) by
letting the LLM call tools that wrap the application services. The ``user_id``
is taken from the authenticated state and passed to the toolkit at dispatch
time — never from the model.
"""

import asyncio
from datetime import UTC, datetime

from langchain_core.messages import AIMessage

from app.agents.context import conversation_messages, user_context_block
from app.agents.nodes.tool_agent_constants import TOOL_AGENT_SYSTEM_PROMPT
from app.agents.state import AgentState
from app.agents.tools.base import Toolkit
from app.core.logging import get_logger
from app.shared.interfaces.llm import LLMConfig, LLMInterface, Message, MessageRole, ToolCall

logger = get_logger(__name__)

# Max tool rounds per turn (cost control): each round the model may request one
# or more tools. Independent tools within a round run concurrently; dependent
# ones span rounds. 4 is ample for personal-finance requests.
MAX_TOOL_ROUNDS = 4


async def tool_agent_node(
    state: AgentState,
    llm: LLMInterface,
    toolkit: Toolkit,
) -> dict[str, object]:
    """Run a bounded tool-calling loop and produce the final response.

    Args:
        state: Current agent state (provides the user message and user_id).
        llm: LLM client supporting tool calling.
        toolkit: Transaction toolkit exposing the callable tools.

    Returns:
        Updated state with the assistant's final message appended.
    """
    user_id = state.get("user_id", "")
    conversation = conversation_messages(state)
    user_message = _last_message(state)
    user_block = user_context_block(state)

    logger.info("Tool agent processing", user_id=user_id, turns=len(conversation))

    try:
        final_text = await _run_tool_loop(
            llm, toolkit, conversation, user_message, user_id, user_block
        )
    except Exception as e:  # noqa: BLE001 - LLM/tool boundary: degrade gracefully.
        logger.error("Tool agent failed", error=str(e))
        final_text = "Lo siento, no pude completar la operación. ¿Puedes intentarlo de nuevo?"

    logger.info("Tool agent responded", answer=final_text[:200])
    # Return only the delta: the add_messages reducer appends the new message.
    return {"messages": [AIMessage(content=final_text)], "should_respond": False}


async def _run_tool_loop(
    llm: LLMInterface,
    toolkit: Toolkit,
    conversation: list[Message],
    user_message: str,
    user_id: str,
    user_block: str = "",
) -> str:
    """Run a bounded ReAct-style tool loop and return the final answer.

    Each round the model may request one or more tools; independent tools are
    executed CONCURRENTLY (``asyncio.gather``) to cut latency. Results are fed
    back as plain conversation text (not the strict tool_call_id protocol), so
    the loop works identically across Groq, Vertex/Gemini, and Cohere. The model
    keeps requesting tools until it has enough, then answers; the round cap is a
    hard backstop against runaway cost.
    """
    # Enough room for a structured, in-depth analysis when the user asks for one.
    config = LLMConfig(temperature=0.2, max_tokens=900)
    # Give the model today's date so it can resolve relative dates ("hoy", "ayer").
    today = datetime.now(UTC).date().isoformat()
    system_prompt = (
        f"{TOOL_AGENT_SYSTEM_PROMPT}\n\n"
        f"La fecha de hoy es {today}. Úsala para interpretar fechas relativas "
        f"como 'hoy' o 'ayer' (formato ISO YYYY-MM-DD).\n"
        "Si necesitas varios datos independientes, pide todas esas herramientas "
        "en el mismo turno para resolverlo más rápido."
        f"{user_block}"
    )
    messages = [Message(role=MessageRole.SYSTEM, content=system_prompt), *conversation]

    for _ in range(MAX_TOOL_ROUNDS):
        response = await llm.generate_with_tools(messages, toolkit.schemas, config)

        if not response.tool_calls:
            return response.content.strip() or "¿En qué puedo ayudarte con tus finanzas?"

        # Execute every tool the model asked for this round, concurrently.
        results = await asyncio.gather(
            *[_safe_dispatch(toolkit, call, user_id) for call in response.tool_calls]
        )
        logger.info("Tool round", tools=[call.name for call in response.tool_calls])
        messages.append(_tool_call_note(response.tool_calls))
        messages.append(_tool_results_message(response.tool_calls, results))

    # Rounds exhausted: force a final plain-text answer from what we gathered.
    return await _force_answer(llm, user_message, messages, config)


def _tool_call_note(calls: list[ToolCall]) -> Message:
    """Record (as assistant text) which tools were called, for loop context."""
    names = ", ".join(call.name for call in calls)
    return Message(role=MessageRole.ASSISTANT, content=f"[Llamé herramientas: {names}]")


def _tool_results_message(calls: list[ToolCall], results: list[str]) -> Message:
    """Feed tool results back as a plain user message (provider-agnostic)."""
    lines = "\n".join(f"- {call.name}: {result}" for call, result in zip(calls, results, strict=False))
    return Message(
        role=MessageRole.USER,
        content=(
            f"Resultados de las herramientas:\n{lines}\n\n"
            "Si necesitas más datos, pide otra herramienta. Si ya tienes lo "
            "necesario, responde al usuario en español de forma clara, usando "
            "únicamente estos resultados (no inventes datos). Para registros o "
            "confirmaciones sé breve; para análisis o consejos, responde "
            "estructurado y a fondo (diagnóstico + recomendaciones)."
        ),
    )


async def _force_answer(
    llm: LLMInterface, user_message: str, messages: list[Message], config: LLMConfig
) -> str:
    """Force a final natural-language answer when the round cap is reached."""
    messages.append(
        Message(
            role=MessageRole.USER,
            content=(
                f'Responde ahora al mensaje original ("{user_message}") en español, '
                "de forma breve y clara, con la información que ya tienes. No inventes datos."
            ),
        )
    )
    try:
        final = await llm.generate(messages, config)
        text = final.content.strip()
        if text:
            return text
    except Exception as e:  # noqa: BLE001 - best-effort final answer.
        logger.error("Tool final answer generation failed", error=str(e))
    return "Reuní la información pero no pude redactar la respuesta. ¿Puedes reformular?"


async def _safe_dispatch(toolkit: Toolkit, call: ToolCall, user_id: str) -> str:
    """Execute a tool call, returning an error message instead of raising."""
    logger.info("Tool call", tool=call.name, args=call.arguments)
    try:
        result = await toolkit.dispatch(call.name, call.arguments, user_id)
    except ValueError as e:
        logger.warning("Tool dispatch error", tool=call.name, error=str(e))
        return f"No pude ejecutar la herramienta solicitada: {e}"
    logger.info("Tool result", tool=call.name, result=result[:200])
    return result


def _last_message(state: AgentState) -> str:
    """Return the content of the last message, if any."""
    messages = state.get("messages", [])
    if not messages:
        return ""
    return getattr(messages[-1], "content", "")
