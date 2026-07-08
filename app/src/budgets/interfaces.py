"""Contracts (ABCs) for the budgets module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal

from app.shared.types import BudgetId, Category, UserId

from .models import Budget, BudgetCreate, BudgetStatus


class BudgetSpendingABC(ABC):
    """Contract for computing how much a user has spent in a period."""

    @abstractmethod
    async def get_spent(
        self,
        user_id: UserId,
        category: Category | None,
        period_start: date,
        period_end: date,
    ) -> Decimal:
        """Return total expenses for the user/category within the period."""


class BudgetRepositoryABC(ABC):
    """Contract for budget persistence (data access only)."""

    @abstractmethod
    async def create(self, budget: BudgetCreate, user_id: UserId) -> Budget:
        """Persist a new budget and return it."""

    @abstractmethod
    async def get_by_id(self, budget_id: BudgetId, user_id: UserId) -> Budget | None:
        """Return a budget owned by ``user_id`` or ``None`` if missing."""

    @abstractmethod
    async def list_page(self, user_id: UserId, *, limit: int, offset: int) -> list[Budget]:
        """Return a page of budgets for a user, newest first."""

    @abstractmethod
    async def count(self, user_id: UserId) -> int:
        """Return the total number of budgets for a user."""

    @abstractmethod
    async def list_active(self, user_id: UserId) -> list[Budget]:
        """Return all active budgets for a user (for alert evaluation)."""

    @abstractmethod
    async def update(
        self,
        budget_id: BudgetId,
        user_id: UserId,
        *,
        name: str | None = None,
        amount: Decimal | None = None,
    ) -> Budget | None:
        """Update a budget's mutable fields; return it, or ``None`` if missing."""

    @abstractmethod
    async def delete(self, budget_id: BudgetId, user_id: UserId) -> Budget | None:
        """Delete a budget; return it, or ``None`` if missing."""


class BudgetServiceABC(ABC):
    """Contract for budget use cases (business logic)."""

    @abstractmethod
    async def create_budget(self, budget: BudgetCreate, user_id: UserId) -> Budget:
        """Create a budget."""

    @abstractmethod
    async def get_budget(self, budget_id: BudgetId, user_id: UserId) -> Budget:
        """Return a budget or raise ``BudgetNotFoundError``."""

    @abstractmethod
    async def list_budgets(
        self, user_id: UserId, *, page: int, page_size: int
    ) -> tuple[list[Budget], int]:
        """Return a page of budgets and the total count."""

    @abstractmethod
    async def get_budget_status(
        self, budget_id: BudgetId, user_id: UserId, as_of: date | None = None
    ) -> BudgetStatus:
        """Return a budget evaluated against current spending."""

    @abstractmethod
    async def get_active_alerts(
        self, user_id: UserId, as_of: date | None = None
    ) -> list[BudgetStatus]:
        """Return the statuses of budgets whose alert threshold is reached."""

    @abstractmethod
    async def get_all_status(
        self, user_id: UserId, as_of: date | None = None
    ) -> list[BudgetStatus]:
        """Return the status (spent vs limit) of every active budget."""

    @abstractmethod
    async def update_budget(
        self,
        budget_id: BudgetId,
        user_id: UserId,
        *,
        name: str | None = None,
        amount: Decimal | None = None,
    ) -> Budget:
        """Change a budget's name/limit or raise ``BudgetNotFoundError``."""

    @abstractmethod
    async def delete_budget(self, budget_id: BudgetId, user_id: UserId) -> Budget:
        """Delete a budget or raise ``BudgetNotFoundError``."""

    @abstractmethod
    async def resolve_budget(self, reference: str, user_id: UserId) -> Budget | None:
        """Find a budget by name or category so the LLM never handles ids."""
