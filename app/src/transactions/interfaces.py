"""Contracts (ABCs) for the transactions module."""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal

from app.shared.types import (
    Category,
    PaymentMethod,
    TransactionId,
    TransactionType,
    UserId,
)

from .models import SpendingSummary, Transaction, TransactionCreate


class TransactionCategorizerABC(ABC):
    """Contract for auto-categorizing a transaction from its description."""

    @abstractmethod
    async def categorize(self, description: str) -> Category:
        """Return the most likely category for ``description``."""


class TransactionRepositoryABC(ABC):
    """Contract for transaction persistence (data access only)."""

    @abstractmethod
    async def create(self, transaction: TransactionCreate, user_id: UserId) -> Transaction:
        """Persist a new transaction and return it."""

    @abstractmethod
    async def get_by_id(
        self, transaction_id: TransactionId, user_id: UserId
    ) -> Transaction | None:
        """Return a transaction owned by ``user_id`` or ``None`` if missing."""

    @abstractmethod
    async def list_page(
        self,
        user_id: UserId,
        *,
        limit: int,
        offset: int,
        transaction_type: TransactionType | None = None,
        category: Category | None = None,
    ) -> list[Transaction]:
        """Return a page of transactions for a user, newest first."""

    @abstractmethod
    async def count(
        self,
        user_id: UserId,
        *,
        transaction_type: TransactionType | None = None,
        category: Category | None = None,
    ) -> int:
        """Return the total number of transactions matching the filters."""

    @abstractmethod
    async def update(
        self, transaction_id: TransactionId, user_id: UserId, data: dict[str, object]
    ) -> Transaction:
        """Apply partial updates to a user's transaction and return it."""

    @abstractmethod
    async def delete(self, transaction_id: TransactionId, user_id: UserId) -> None:
        """Delete a user's transaction (scoped by ``user_id``)."""


class TransactionServiceABC(ABC):
    """Contract for transaction use cases (business logic)."""

    @abstractmethod
    async def create_transaction(
        self, transaction: TransactionCreate, user_id: UserId
    ) -> Transaction:
        """Create a transaction, auto-categorizing it when no category is given."""

    @abstractmethod
    async def get_transaction(
        self, transaction_id: TransactionId, user_id: UserId
    ) -> Transaction:
        """Return a transaction or raise ``TransactionNotFoundError``."""

    @abstractmethod
    async def list_transactions(
        self,
        user_id: UserId,
        *,
        page: int,
        page_size: int,
        transaction_type: TransactionType | None = None,
        category: Category | None = None,
    ) -> tuple[list[Transaction], int]:
        """Return a page of transactions and the total count."""

    @abstractmethod
    async def update_transaction(
        self,
        transaction_id: TransactionId,
        user_id: UserId,
        *,
        amount: Decimal | None = None,
        description: str | None = None,
        category: Category | None = None,
        transaction_type: TransactionType | None = None,
        transaction_date: date | None = None,
        payment_method: PaymentMethod | None = None,
    ) -> Transaction:
        """Update the given fields of a transaction (or raise if not found)."""

    @abstractmethod
    async def delete_transaction(
        self, transaction_id: TransactionId, user_id: UserId
    ) -> Transaction:
        """Delete a transaction and return it (or raise if not found)."""

    @abstractmethod
    async def get_spending_summary(
        self, user_id: UserId, *, period_start: date, period_end: date
    ) -> SpendingSummary:
        """Aggregate income and expenses-by-category for a date range."""
