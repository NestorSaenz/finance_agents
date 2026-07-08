"""Dependency injection wiring for the memory module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep, get_llm_simple
from app.shared.interfaces.llm import LLMInterface

from .interfaces import MemoryAgentServiceABC, UserKnowledgeRepositoryABC
from .repositories.user_knowledge_repository import UserKnowledgeRepository
from .services.memory_agent_service import MemoryAgentService


def get_user_knowledge_repository(db: DatabaseDep) -> UserKnowledgeRepositoryABC:
    """Provide the user-knowledge repository."""
    return UserKnowledgeRepository(db)


def get_memory_agent_service(
    repository: Annotated[UserKnowledgeRepositoryABC, Depends(get_user_knowledge_repository)],
) -> MemoryAgentServiceABC:
    """Provide the memory agent service (uses the fast LLM for extraction)."""
    llm: LLMInterface = get_llm_simple()
    return MemoryAgentService(repository, llm)


MemoryAgentServiceDep = Annotated[MemoryAgentServiceABC, Depends(get_memory_agent_service)]
