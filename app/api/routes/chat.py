"""Chat endpoints for conversational interaction."""

import asyncio
import base64
import binascii
import uuid
from typing import Annotated, Any, Final, Protocol

from fastapi import APIRouter, Depends
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, Field, model_validator

from app.agents.constants import GRAPH_RECURSION_LIMIT, GRAPH_TIMEOUT_SECONDS
from app.agents.graph import get_compiled_graph
from app.agents.nodes.image_ingestion import (
    ImageIngestionService,
    ImageIngestionServiceABC,
)
from app.agents.state import build_initial_state
from app.core.config import settings
from app.core.logging import get_logger
from app.core.observability import get_trace_callbacks
from app.shared.dependencies import LLMVisionDep
from app.src.auth.dependencies import CurrentUserId
from app.src.chat.dependencies import ChatMemoryServiceDep
from app.src.chat.models import ChatMessage
from app.src.memory.dependencies import MemoryAgentServiceDep
from app.src.ratelimit.dependencies import RateLimitServiceDep
from app.src.users.dependencies import UserProfileServiceDep

logger = get_logger(__name__)

router = APIRouter()

# Accepted attachment types (image or PDF) and max decoded size for ingestion uploads.
ALLOWED_ATTACHMENT_MIME_TYPES: Final[frozenset[str]] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "application/pdf"}
)
MAX_IMAGE_BYTES: Final[int] = 8 * 1024 * 1024  # 8 MB (decoded)
# Reject oversized payloads before decoding: base64 inflates size by ~4/3 plus padding.
MAX_IMAGE_BASE64_CHARS: Final[int] = 12 * 1024 * 1024  # ~12 MB of base64 text


def get_ingestion_service(llm: LLMVisionDep) -> ImageIngestionServiceABC:
    """Provide the image ingestion service, wired to a vision-capable LLM."""
    return ImageIngestionService(llm)


IngestionDep = Annotated[ImageIngestionServiceABC, Depends(get_ingestion_service)]


class InvokableGraph(Protocol):
    """Minimal contract used by the chat route: an async-invokable graph."""

    async def ainvoke(self, state: Any, config: dict[str, Any]) -> dict[str, Any]:
        ...


# Graph is resolved through a dependency so tests can override it with a graph
# built from mocked clients (app.dependency_overrides).
GraphDep = Annotated[InvokableGraph, Depends(get_compiled_graph)]

FALLBACK_RESPONSE = (
    "Lo siento, tuve un problema procesando tu solicitud. "
    "Por favor, inténtalo de nuevo en un momento."
)


class ChatRequest(BaseModel):
    """Request model for chat endpoint.

    Either ``message`` or ``image`` (or both) must be present. An image triggers
    the ingestion flow (extract movements from a photo/screenshot of a sheet).
    """

    message: str = Field("", max_length=2000, description="User message")
    session_id: str | None = Field(None, description="Conversation id to continue")
    image: str | None = Field(
        None,
        max_length=MAX_IMAGE_BASE64_CHARS,
        description="Base64-encoded image (optional)",
    )
    image_mime_type: str | None = Field(
        None, description="Image MIME type, e.g. image/jpeg"
    )

    @model_validator(mode="after")
    def _require_message_or_image(self) -> "ChatRequest":
        if not self.message.strip() and not self.image:
            raise ValueError("Provide a message or an image.")
        return self


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    response: str = Field(..., description="Assistant response")
    session_id: str = Field(..., description="Conversation id (send it back to continue)")
    agent_used: str | None = Field(None, description="Which agent handled the request")


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    graph: GraphDep,
    user_id: CurrentUserId,
    memory: ChatMemoryServiceDep,
    memory_agent: MemoryAgentServiceDep,
    profiles: UserProfileServiceDep,
    ingestion: IngestionDep,
    rate_limiter: RateLimitServiceDep,
) -> ChatResponse:
    """Send a message to the FinanceGPT assistant.

    Resolves the user's conversation, feeds the recent history and the user's
    long-term memory to the multiagent graph, and persists the turn. Data is
    scoped to ``user_id``.

    Args:
        request: Chat request with the user message and optional conversation id.
        graph: Compiled multiagent graph (injected).
        user_id: Authenticated user id (injected).
        memory: Conversation memory service (injected).
        memory_agent: Long-term memory agent (injected).

    Returns:
        Assistant response and the conversation id to continue with.
    """
    # Cap chat usage per user (LLM cost / abuse control) before doing any work.
    # Runs before the graph try/except below, so an over-limit turn propagates to
    # the exception handler as a 429 instead of being swallowed as a graph error.
    await rate_limiter.check_chat(user_id, has_image=bool(request.image))

    conversation_id, history = await _load_context(memory, user_id, request.session_id)
    user_context = await _build_user_context(memory_agent, profiles, user_id)

    logger.info(
        "Chat request received",
        user_id=user_id,
        conversation_id=conversation_id,
        history=len(history),
        has_memory=bool(user_context),
        has_image=bool(request.image),
    )

    # An attached image goes through the dedicated ingestion flow (extract + propose),
    # bypassing the classifier/tool graph.
    if request.image:
        return await _handle_image(
            request, ingestion, memory, conversation_id, user_id, user_context
        )

    initial_state = build_initial_state(
        message=request.message,
        user_id=user_id,
        history=history,
        user_context=user_context,
    )
    # Fresh thread id per request: history is injected explicitly, so the
    # in-memory checkpointer must not also carry it over. recursion_limit is a
    # hard backstop against runaway loops (cost control).
    config: dict[str, Any] = {
        "configurable": {"thread_id": uuid.uuid4().hex},
        "recursion_limit": GRAPH_RECURSION_LIMIT,
    }

    # Attach Langfuse tracing (no-op if not configured): one trace per turn,
    # grouped by user and conversation for the Sessions/Users views.
    callbacks = get_trace_callbacks()
    if callbacks:
        config["callbacks"] = callbacks
        config["run_name"] = "financegpt-chat"
        config["metadata"] = {
            "langfuse_user_id": user_id,
            "langfuse_session_id": conversation_id,
            # Tags let us filter prod vs local/test traces in Langfuse.
            "langfuse_tags": [f"env:{settings.ENVIRONMENT}", "channel:chat"],
        }

    try:
        final_state = await asyncio.wait_for(
            graph.ainvoke(initial_state, config=config), timeout=GRAPH_TIMEOUT_SECONDS
        )
    except TimeoutError:
        logger.error("Graph invocation timed out", conversation_id=conversation_id)
        return ChatResponse(
            response=FALLBACK_RESPONSE, session_id=conversation_id, agent_used="timeout"
        )
    except Exception as e:  # noqa: BLE001 - LLM/graph boundary: degrade gracefully.
        logger.error("Graph invocation failed", conversation_id=conversation_id, error=str(e))
        return ChatResponse(
            response=FALLBACK_RESPONSE, session_id=conversation_id, agent_used="error"
        )

    response_text = _extract_response(final_state)

    # Persist the turn and extract long-term memory without blocking (best-effort).
    _fire_and_forget(
        memory.save_turn(conversation_id, user_id, request.message, response_text)
    )
    _fire_and_forget(memory_agent.process(user_id, request.message, response_text))

    return ChatResponse(
        response=response_text,
        session_id=conversation_id,
        agent_used=final_state.get("detected_intent"),
    )


async def _handle_image(
    request: ChatRequest,
    ingestion: ImageIngestionServiceABC,
    memory: ChatMemoryServiceDep,
    conversation_id: str,
    user_id: str,
    user_context: str,
) -> ChatResponse:
    """Extract movements from an attached image and propose them for confirmation."""
    mime_type = (request.image_mime_type or "").lower()
    if mime_type not in ALLOWED_ATTACHMENT_MIME_TYPES:
        return ChatResponse(
            response="Ese formato no es válido. Envíame un JPG, PNG, WebP o PDF.",
            session_id=conversation_id,
            agent_used="ingestion",
        )

    try:
        image_bytes = base64.b64decode(request.image or "", validate=True)
    except (binascii.Error, ValueError):
        return ChatResponse(
            response="No pude leer la imagen. ¿La puedes enviar de nuevo?",
            session_id=conversation_id,
            agent_used="ingestion",
        )
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        return ChatResponse(
            response="La imagen es muy pesada o está vacía. Prueba con una más liviana (máx. 8 MB).",
            session_id=conversation_id,
            agent_used="ingestion",
        )

    # The accompanying note ("estos son de mi tarjeta Nu") tells the extractor the
    # payment method/card, so it doesn't get asked again at registration.
    note = request.message.strip()
    proposal = await ingestion.propose(image_bytes, mime_type, user_context, note)

    # Persist the turn so the user's confirmation next message can register the batch
    # (the tool agent reads the proposal from history). Best-effort.
    user_message = note or "(imagen adjunta)"
    _fire_and_forget(memory.save_turn(conversation_id, user_id, user_message, proposal))

    return ChatResponse(
        response=proposal, session_id=conversation_id, agent_used="ingestion"
    )


async def _build_user_context(
    memory_agent: MemoryAgentServiceDep,
    profiles: UserProfileServiceDep,
    user_id: str,
) -> str:
    """Compose the user context: their name (if known) + long-term memory facts.

    Both parts are best-effort so the chat never fails if one lookup breaks.
    """
    facts = await memory_agent.get_context(user_id)
    try:
        profile = await profiles.get_profile(user_id)
        name = (profile.display_name or "").strip()
        currency = (profile.currency or "").strip()
    except Exception as e:  # noqa: BLE001 - profile is best-effort context.
        logger.warning("Could not load profile", error=str(e))
        name = ""
        currency = ""

    parts: list[str] = []
    if name:
        parts.append(f"El usuario se llama {name}.")
    if facts:
        parts.append(facts)
    if currency:
        parts.append(f"Moneda del usuario: {currency}.")
    return "\n".join(parts)


async def _load_context(
    memory: ChatMemoryServiceDep, user_id: str, session_id: str | None
) -> tuple[str, list[BaseMessage]]:
    """Resolve the conversation and load its recent history (resilient)."""
    try:
        conversation_id = await memory.resolve_conversation(user_id, session_id)
        history = _to_langchain(await memory.load_history(conversation_id, user_id))
        return conversation_id, history
    except Exception as e:  # noqa: BLE001 - memory is best-effort; proceed without it.
        logger.warning("Chat memory unavailable; proceeding without history", error=str(e))
        return session_id or uuid.uuid4().hex, []


def _to_langchain(messages: list[ChatMessage]) -> list[BaseMessage]:
    """Convert stored messages to LangChain messages for the graph state."""
    result: list[BaseMessage] = []
    for message in messages:
        if message.role == "assistant":
            result.append(AIMessage(content=message.content))
        else:
            result.append(HumanMessage(content=message.content))
    return result


def _fire_and_forget(coro: Any) -> None:
    """Run a coroutine in the background, logging (not raising) on failure."""
    task = asyncio.create_task(coro)
    task.add_done_callback(_log_task_exception)


def _log_task_exception(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    error = task.exception()
    if error:
        logger.error("Background task failed", error=str(error))


def _extract_response(state: dict) -> str:
    """Extract the assistant's reply (last AI message) from the final state."""
    messages = state.get("messages", [])
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, str) and content.strip():
                return content
    return FALLBACK_RESPONSE
