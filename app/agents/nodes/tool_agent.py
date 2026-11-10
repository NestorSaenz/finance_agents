"""Tool-calling agent node.

Handles actionable intents (register a transaction, query transactions) by
letting the LLM call tools that wrap the application services. The ``user_id``
is taken from the authenticated state and passed to the toolkit at dispatch
time — never from the model.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import date
from decimal import Decimal
from typing import Final, NamedTuple

from langchain_core.messages import AIMessage

from app.agents.context import (
    category_context_block,
    prior_context,
    user_context_block,
)
from app.agents.nodes.action_claims import (
    DISPATCH_ERROR_PREFIX,
    MUTATING_TOOLS,
    enforce_truthful_reply,
    is_write_attempt,
    is_write_refused,
)
from app.agents.nodes.tool_agent_constants import NO_HISTORY_BLOCK, TOOL_AGENT_SYSTEM_PROMPT
from app.agents.state import AgentState
from app.agents.tools.base import Toolkit
from app.agents.tools.names import (
    CREATE_BUDGET_TOOL,
    CREATE_GOAL_TOOL,
    CREATE_RECURRING_TOOL,
    MANAGE_CATEGORY_TOOL,
    REGISTER_TRANSACTION_TOOL,
)
from app.core.logging import get_logger
from app.core.observability import record_tool_span, start_tool_span
from app.shared.clock import bound_today, current_today, local_today
from app.shared.interfaces.llm import LLMConfig, LLMInterface, Message, MessageRole, ToolCall
from app.shared.turn import TurnContext, bound_turn

logger = get_logger(__name__)

# Max tool rounds per turn (cost control): each round the model may request one
# or more tools. Independent tools within a round run concurrently; dependent
# ones span rounds. 4 is ample for personal-finance requests.
MAX_TOOL_ROUNDS = 4

# Result for a write the model re-sent (same tool and args) in a LATER round of the
# same turn: it is not executed again, so a model that loops cannot duplicate records.
DUPLICATE_WRITE_RESULT: Final = (
    "No la ejecuté otra vez: ya hiciste exactamente esta operación en este turno. Si el "
    "usuario pidió registrarla dos veces, díselo y pregúntale si quiere el segundo; si no, "
    "responde sin repetirla."
)

# Real defaults of the mutating tools' optional arguments (taken from each tool's code),
# so repeat detection treats an explicit default and an omitted argument as the same call.
_TOOL_DEFAULTS: Final[dict[str, dict[str, object]]] = {
    REGISTER_TRANSACTION_TOOL: {"transaction_type": "expense", "cuotas": 1},
    CREATE_RECURRING_TOOL: {"transaction_type": "expense", "frequency": "monthly"},
    CREATE_BUDGET_TOOL: {"period_type": "monthly"},
    CREATE_GOAL_TOOL: {"goal_type": "savings"},
    MANAGE_CATEGORY_TOOL: {"delete_movements": False},
}

# Fetches the user's existing categories so the agent can reuse them (injected
# via binding, like llm/toolkit). Optional: tests and simple wiring may omit it.
CategoriesProvider = Callable[[str], Awaitable[list[str]]]


async def _fetch_categories(provider: CategoriesProvider | None, user_id: str) -> list[str]:
    """Best-effort fetch of the user's categories; never breaks the turn."""
    if provider is None:
        return []
    try:
        return await provider(user_id)
    except Exception as e:  # noqa: BLE001 - context enrichment must not break the turn.
        logger.warning("Could not load user categories", error=str(e))
        return []


async def tool_agent_node(
    state: AgentState,
    llm: LLMInterface,
    toolkit: Toolkit,
    categories_provider: CategoriesProvider | None = None,
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
    # History (prior turns) goes into the prompt as labeled CONTEXT; only the
    # current message is the actionable instruction. This stops the model from
    # re-executing a past turn's action (e.g. re-registering a previous expense)
    # when the user asks for something unrelated.
    history = prior_context(state)
    user_message = _last_message(state)
    # Inject the user's existing categories so the agent reuses them (prevents a
    # synonym like "medicamentos" spawning a duplicate of "consultas y medicamentos").
    categories = await _fetch_categories(categories_provider, user_id)
    user_block = user_context_block(state) + category_context_block(categories)

    logger.info("Tool agent processing", user_id=user_id, turns=len(history))

    # Resolve the user's local "today" ONCE for this turn. The SAME value feeds
    # the system prompt (so the model reads relative dates like "hoy"/"ayer" in
    # the user's day) AND the request-scoped ContextVar every dispatched tool
    # reads — prompt-today and tool-today can never disagree. Empty timezone →
    # None → UTC fallback (no warning) for callers that don't set one.
    today = local_today(state.get("timezone") or None)

    turn_failed = False
    try:
        # Bind the turn so two-step tools (propose now, confirm later) know which
        # request they run in. Without ids nothing is bound and those tools fail closed.
        with _turn_scope(state):
            final_text = await _run_tool_loop(
                llm, toolkit, history, user_message, user_id, user_block, today
            )
    except Exception as e:  # noqa: BLE001 - LLM/tool boundary: degrade gracefully.
        logger.error("Tool agent failed", error=str(e))
        final_text = "Lo siento, no pude completar la operación. ¿Puedes intentarlo de nuevo?"
        turn_failed = True

    logger.info("Tool agent responded", answer=final_text[:200])
    # Return only the delta: the add_messages reducer appends the new message.
    return {
        "messages": [AIMessage(content=final_text)],
        "should_respond": False,
        "turn_failed": turn_failed,
    }


def _turn_scope(state: AgentState) -> AbstractContextManager[None]:
    """Bind the state's turn/conversation ids, or nothing when either is missing."""
    turn_id = state.get("turn_id", "")
    conversation_id = state.get("conversation_id", "")
    if not turn_id or not conversation_id:
        return nullcontext()
    return bound_turn(TurnContext(turn_id=turn_id, conversation_id=conversation_id))


async def _run_tool_loop(
    llm: LLMInterface,
    toolkit: Toolkit,
    history: list[Message],
    user_message: str,
    user_id: str,
    user_block: str = "",
    today: date | None = None,
) -> str:
    """Run a bounded ReAct-style tool loop and return the final answer.

    Each round the model may request one or more tools; independent tools are
    executed CONCURRENTLY (``asyncio.gather``) to cut latency. Results are fed
    back as plain conversation text (not the strict tool_call_id protocol), so
    the loop works identically across Groq, Vertex/Gemini, and Cohere. The model
    keeps requesting tools until it has enough, then answers; the round cap is a
    hard backstop against runaway cost.

    ``today`` is the user's local calendar day (resolved once by the caller). It
    is stamped into the prompt AND bound to the request-scoped ContextVar so every
    dispatched tool defaults omitted dates to the SAME day. Defaults to UTC today
    for callers that omit it.
    """
    # Enough room for a structured, in-depth analysis when the user asks for one.
    config = LLMConfig(temperature=0.2, max_tokens=900)
    day = today or current_today()
    # Give the model today's date so it can resolve relative dates ("hoy", "ayer").
    system_prompt = (
        f"{TOOL_AGENT_SYSTEM_PROMPT}\n\n"
        f"La fecha de hoy es {day.isoformat()}. Úsala para interpretar fechas relativas "
        f"como 'hoy' o 'ayer' (formato ISO YYYY-MM-DD).\n"
        "Si necesitas varios datos independientes, pide todas esas herramientas "
        "en el mismo turno para resolverlo más rápido."
        f"{user_block}"
        f"{_history_block(history)}"
    )
    # The current message is the ONLY actionable instruction; prior turns live in
    # the system prompt as context, so they can't be mistaken for new requests.
    messages = [
        Message(role=MessageRole.SYSTEM, content=system_prompt),
        Message(role=MessageRole.USER, content=user_message),
    ]

    # Bind the SAME day the prompt carries so every tool dispatched below reads it
    # via current_today() — without threading it through dispatch (security contract).
    # A write counts as applied once a mutating tool ran and reported it; a claim in a
    # turn where NO tool ran at all is invented and gets replaced (see action_claims).
    write_attempted = False
    write_refused = False
    tools_called: list[str] = []
    history_text = "\n".join(message.content for message in history)
    assistant_text = "\n".join(
        message.content for message in history if message.role == MessageRole.ASSISTANT
    )
    executed_writes: set[tuple[str, str]] = set()  # mutating calls run in earlier rounds
    with bound_today(day):
        for _ in range(MAX_TOOL_ROUNDS):
            response = await llm.generate_with_tools(messages, toolkit.schemas, config)

            if not response.tool_calls:
                text = response.content.strip() or "¿En qué puedo ayudarte con tus finanzas?"
                return enforce_truthful_reply(
                    text,
                    write_attempted=write_attempted,
                    write_refused=write_refused,
                    tools_called=tools_called,
                    history_text=history_text,
                    history_claims_text=assistant_text,
                )

            # Execute every tool the model asked for this round, concurrently.
            outcome = await _dispatch_round(toolkit, response.tool_calls, user_id, executed_writes)
            results = outcome.results
            # Only calls that really ran count: a skipped repeat is not a new write (the
            # earlier identical call already counted).
            write_attempted |= any(
                is_write_attempt(call.name, result)
                for call, result in zip(outcome.ran, outcome.ran_results, strict=True)
            )
            write_refused |= any(
                is_write_refused(call.name, result)
                for call, result in zip(outcome.ran, outcome.ran_results, strict=True)
            )
            tools_called.extend(call.name for call in outcome.ran)
            logger.info("Tool round", tools=[call.name for call in response.tool_calls])
            messages.append(_tool_call_note(response.tool_calls))
            messages.append(_tool_results_message(response.tool_calls, results))

        # Rounds exhausted: force a final plain-text answer from what we gathered.
        forced = await _force_answer(llm, user_message, messages, config)
        return enforce_truthful_reply(
            forced,
            write_attempted=write_attempted,
            write_refused=write_refused,
            tools_called=tools_called,
            history_text=history_text,
            history_claims_text=assistant_text,
        )


def _history_block(history: list[Message]) -> str:
    """Render prior turns as a labeled transcript for the system prompt.

    Kept as CONTEXT (not as live user/assistant messages) so the model resolves
    references ("ese gasto", "la meta") without treating a past instruction as a
    new one to act on. The current message is passed separately as the only
    actionable turn.
    """
    if not history:
        return NO_HISTORY_BLOCK
    lines = [
        f"{'Safi' if message.role == MessageRole.ASSISTANT else 'Usuario'}: {message.content}"
        for message in history
    ]
    return (
        "\n\n## Conversación previa (contexto). Reglas al leerla:\n"
        "- Las transacciones, pagos o metas que en turnos anteriores YA quedaron "
        "REGISTRADOS no se vuelven a registrar: no los repitas.\n"
        "- PERO si tu último turno fue una PREGUNTA (p. ej. '¿efectivo o crédito?', "
        "'¿con cuál tarjeta?', '¿qué categoría?'), el mensaje ACTUAL del usuario es la "
        "RESPUESTA: completa esa acción pendiente ahora (aún no estaba registrada).\n"
        "- Actúa solo sobre el mensaje actual del usuario, no sobre pedidos ya resueltos.\n\n"
        "Transcripción:\n" + "\n".join(lines)
    )


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


class _RoundOutcome(NamedTuple):
    results: list[str]  # one per requested call, in order (skipped repeats included)
    ran: list[ToolCall]  # the calls that were actually executed
    ran_results: list[str]


def _canonical(value: object) -> object:
    """Canonical form of an argument value, for comparing calls (never for executing them).

    Numbers (not bool) become their normalized decimal string, so 5, 5.0 and Decimal("5")
    agree; strings are stripped and case-folded; containers are canonicalized recursively.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float | Decimal):
        return format(Decimal(str(value)).normalize(), "f")
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_canonical(v) for v in value]
    return value


def _call_key(call: ToolCall) -> tuple[str, str]:
    """Identity of a call for repeat detection: tool name + canonical (sorted) args.

    An argument that is absent, ``None`` or ``""`` equals one that is omitted, and one
    equal to its tool's real default (``_TOOL_DEFAULTS``) equals omitting it, so a retry
    that spells the defaults differently is still recognized as the same write.
    """
    defaults = _TOOL_DEFAULTS.get(call.name, {})
    canonical = {
        key: _canonical(value)
        for key, value in call.arguments.items()
        if value is not None and value != ""
    }
    for key, default in defaults.items():
        if canonical.get(key) == _canonical(default):
            del canonical[key]
    return call.name, json.dumps(canonical, sort_keys=True, default=str)


async def _dispatch_round(
    toolkit: Toolkit,
    calls: list[ToolCall],
    user_id: str,
    executed_writes: set[tuple[str, str]],
) -> _RoundOutcome:
    """Run one round's calls concurrently, skipping writes already run in an EARLIER round.

    Identical writes inside the SAME round all run (a statement can hold two equal
    charges); only a repeat in a later round is replaced by ``DUPLICATE_WRITE_RESULT``.
    Read-only tools are never skipped. Only writes that APPLIED are recorded for later
    rounds: a refused or failed call may legitimately be retried and gets the same answer.
    """
    is_repeat = [
        call.name in MUTATING_TOOLS and _call_key(call) in executed_writes for call in calls
    ]
    for call, repeated in zip(calls, is_repeat, strict=True):
        if repeated:
            logger.warning("Skipped repeated write in the same turn", tool=call.name)
    ran = [call for call, repeated in zip(calls, is_repeat, strict=True) if not repeated]
    ran_results = list(await asyncio.gather(*[_safe_dispatch(toolkit, c, user_id) for c in ran]))
    executed_writes.update(
        _call_key(call)
        for call, result in zip(ran, ran_results, strict=True)
        if is_write_attempt(call.name, result)
    )
    fresh = iter(ran_results)
    results = [DUPLICATE_WRITE_RESULT if repeated else next(fresh) for repeated in is_repeat]
    return _RoundOutcome(results, ran, ran_results)


async def _safe_dispatch(toolkit: Toolkit, call: ToolCall, user_id: str) -> str:
    """Execute a tool call, returning an error message instead of raising.

    The execution is wrapped in a Langfuse span (``tool:<name>``) so the trace
    shows each tool's input, result and latency — not just the LLM's decision to
    call it. The span nests under the current agent run and is a no-op when
    tracing is disabled.
    """
    logger.info("Tool call", tool=call.name, args=call.arguments)
    with start_tool_span(f"tool:{call.name}", call.arguments) as span:
        try:
            result = await toolkit.dispatch(call.name, call.arguments, user_id)
        except ValueError as e:
            logger.warning("Tool dispatch error", tool=call.name, error=str(e))
            message = f"{DISPATCH_ERROR_PREFIX}: {e}"
            record_tool_span(span, output=message, error=str(e))
            return message
        logger.info("Tool result", tool=call.name, result=result[:200])
        record_tool_span(span, output=result)
        return result


def _last_message(state: AgentState) -> str:
    """Return the content of the last message, if any."""
    messages = state.get("messages", [])
    if not messages:
        return ""
    return getattr(messages[-1], "content", "")
