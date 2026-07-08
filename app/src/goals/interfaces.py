"""Contracts (ABCs) for the goals module."""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any

from app.shared.types import GoalId, UserId

from .models import Goal, GoalCreate, GoalProgress


class GoalRepositoryABC(ABC):
    """Contract for goal persistence (data access only)."""

    @abstractmethod
    async def create(self, goal: GoalCreate, user_id: UserId) -> Goal:
        """Persist a new goal and return it."""

    @abstractmethod
    async def get_by_id(self, goal_id: GoalId, user_id: UserId) -> Goal | None:
        """Return a goal owned by ``user_id`` or ``None`` if missing."""

    @abstractmethod
    async def list_page(self, user_id: UserId, *, limit: int, offset: int) -> list[Goal]:
        """Return a page of goals for a user, by priority then newest."""

    @abstractmethod
    async def count(self, user_id: UserId) -> int:
        """Return the total number of goals for a user."""

    @abstractmethod
    async def update(
        self, goal_id: GoalId, user_id: UserId, data: dict[str, Any]
    ) -> Goal:
        """Apply partial updates to a goal and return the updated goal."""

    @abstractmethod
    async def delete(self, goal_id: GoalId, user_id: UserId) -> None:
        """Delete a user's goal (scoped by ``user_id``)."""


class GoalServiceABC(ABC):
    """Contract for goal use cases (business logic)."""

    @abstractmethod
    async def create_goal(self, goal: GoalCreate, user_id: UserId) -> Goal:
        """Create a financial goal."""

    @abstractmethod
    async def get_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        """Return a goal or raise ``GoalNotFoundError``."""

    @abstractmethod
    async def list_goals(
        self, user_id: UserId, *, page: int, page_size: int
    ) -> tuple[list[Goal], int]:
        """Return a page of goals and the total count."""

    @abstractmethod
    async def contribute(self, goal_id: GoalId, user_id: UserId, amount: Decimal) -> Goal:
        """Add ``amount`` to a goal's current amount, completing it if reached."""

    @abstractmethod
    async def get_progress(
        self, goal_id: GoalId, user_id: UserId, as_of: date | None = None
    ) -> GoalProgress:
        """Return a goal evaluated against its target and timeline."""

    @abstractmethod
    async def delete_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        """Delete a goal and return it (or raise ``GoalNotFoundError``)."""
