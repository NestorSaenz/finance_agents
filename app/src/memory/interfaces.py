"""Contracts (ABCs) for the memory module."""

from abc import ABC, abstractmethod

from app.shared.types import UserId

from .models import KnowledgeEntry


class UserKnowledgeRepositoryABC(ABC):
    """Contract for persisting the user's long-term knowledge."""

    @abstractmethod
    async def get_all(self, user_id: UserId) -> list[KnowledgeEntry]:
        """Return all knowledge facts for a user."""

    @abstractmethod
    async def upsert_many(self, user_id: UserId, entries: list[KnowledgeEntry]) -> None:
        """Insert or update knowledge facts (by user_id + key)."""


class MemoryAgentServiceABC(ABC):
    """Contract for the long-term memory agent."""

    @abstractmethod
    async def process(
        self, user_id: UserId, user_message: str, assistant_message: str
    ) -> None:
        """Extract durable facts from a turn and store them (best-effort)."""

    @abstractmethod
    async def get_context(self, user_id: UserId) -> str:
        """Return the user's stored knowledge as a compact context string."""
