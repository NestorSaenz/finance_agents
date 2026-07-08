"""Contracts (ABCs) for the chat memory module."""

from abc import ABC, abstractmethod

from app.shared.types import UserId

from .models import ChatMessage


class ConversationRepositoryABC(ABC):
    """Contract for conversation/message persistence (data access only)."""

    @abstractmethod
    async def create_conversation(self, user_id: UserId) -> str:
        """Create a new conversation and return its id."""

    @abstractmethod
    async def get_owner(self, conversation_id: str) -> str | None:
        """Return the user_id owning a conversation, or None if it doesn't exist."""

    @abstractmethod
    async def get_recent_messages(
        self, conversation_id: str, user_id: UserId, limit: int
    ) -> list[ChatMessage]:
        """Return the latest ``limit`` messages for the user, oldest first."""

    @abstractmethod
    async def save_messages(
        self, conversation_id: str, user_id: UserId, messages: list[ChatMessage]
    ) -> None:
        """Persist messages for a conversation."""


class ChatMemoryServiceABC(ABC):
    """Contract for conversation memory (short-term)."""

    @abstractmethod
    async def resolve_conversation(self, user_id: UserId, session_id: str | None) -> str:
        """Return an existing conversation id owned by the user, or create one."""

    @abstractmethod
    async def load_history(self, conversation_id: str, user_id: UserId) -> list[ChatMessage]:
        """Load the recent conversation history for context (scoped to the user)."""

    @abstractmethod
    async def save_turn(
        self, conversation_id: str, user_id: UserId, user_message: str, assistant_message: str
    ) -> None:
        """Persist a user+assistant turn (best-effort; never raises)."""
