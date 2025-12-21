"""Chat endpoints for conversational interaction."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    session_id: str | None = Field(None, description="Session ID for conversation continuity")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""

    response: str = Field(..., description="Assistant response")
    session_id: str = Field(..., description="Session ID")
    agent_used: str | None = Field(None, description="Which agent handled the request")


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the FinanceGPT assistant.

    The message will be processed by the multiagent system which will:
    1. Interpret the user's intent
    2. Route to the appropriate specialized agent
    3. Generate a contextual response

    Args:
        request: Chat request with user message

    Returns:
        Assistant response with metadata
    """
    logger.info("Chat request received", message_length=len(request.message))

    # TODO: Implement actual agent invocation
    # For now, return a placeholder response

    return ChatResponse(
        response="¡Hola! Soy FinanceGPT, tu asistente financiero personal. "
        "Todavía estoy en desarrollo, pero pronto podré ayudarte a gestionar tus finanzas. "
        f"Recibí tu mensaje: '{request.message[:50]}...'",
        session_id=request.session_id or "new-session",
        agent_used="orchestrator",
    )
