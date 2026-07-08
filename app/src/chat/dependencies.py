"""Dependency injection wiring for the chat memory module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep

from .interfaces import ChatMemoryServiceABC, ConversationRepositoryABC
from .repositories.conversation_repository import ConversationRepository
from .services.chat_memory_service import ChatMemoryService


def get_conversation_repository(db: DatabaseDep) -> ConversationRepositoryABC:
    """Provide the conversation repository."""
    return ConversationRepository(db)


def get_chat_memory_service(
    repository: Annotated[ConversationRepositoryABC, Depends(get_conversation_repository)],
) -> ChatMemoryServiceABC:
    """Provide the chat memory service."""
    return ChatMemoryService(repository)


ChatMemoryServiceDep = Annotated[ChatMemoryServiceABC, Depends(get_chat_memory_service)]
