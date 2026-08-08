"""Contracts (ABCs) for the transactions module."""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal

from app.shared.types import (
    CardId,
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
        card_id: CardId | None = None,
    ) -> list[Transaction]:
        """Return a page of transactions for a user, newest first."""

    @abstractmethod
    async def count(
        self,
        user_id: UserId,
        *,
        transaction_type: TransactionType | None = None,
        category: Category | None = None,
        card_id: CardId | None = None,
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

    @abstractmethod
    async def recategorize(self, user_id: UserId, old: Category, new: Category) -> int:
        """Reassign every transaction in ``old`` to ``new``; return rows changed."""

    @abstractmethod
    async def delete_by_category(self, user_id: UserId, category: Category) -> int:
        """Delete every transaction in ``category``; return rows deleted."""


class TransactionServiceABC(ABC):
    """Contract for transaction use cases (business logic)."""

    @abstractmethod
    async def create_transaction(
        self, transaction: TransactionCreate, user_id: UserId
    ) -> Transaction:
        """Create a transaction, auto-categorizing it when no category is given."""

    @abstractmethod
    async def create_installments(
        self, base: TransactionCreate, installments: int, user_id: UserId
    ) -> list[Transaction]:
        """Split a deferred purchase into ``installments`` monthly transactions.

        The purchase total is divided across the installments (first at the base
        date, each next one a month later) so a budget sees the per-month cost.
        """

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
        card_id: CardId | None = None,
    ) -> tuple[list[Transaction], int]:
        """Return a page of transactions and the total count."""

    @abstractmethod
    async def resolve_category(self, proposed: Category, user_id: UserId) -> Category:
        """Snap a proposed category onto one the user already uses when close.

        Reuses the existing spelling on an exact or high-similarity match (typo
        tolerance) so a variant like "improvistos" does not fragment the user's
        existing "imprevistos"; otherwise returns the normalized proposal.
        """

    @abstractmethod
    async def list_categories(self, user_id: UserId) -> list[Category]:
        """Distinct categories the user has used (for reuse/injection)."""

    @abstractmethod
    async def count_by_category(self, user_id: UserId, category: Category) -> int:
        """Number of the user's transactions in ``category``."""

    @abstractmethod
    async def recategorize(self, user_id: UserId, old: Category, new: Category) -> int:
        """Move every transaction from category ``old`` to ``new``; rows changed."""

    @abstractmethod
    async def delete_by_category(self, user_id: UserId, category: Category) -> int:
        """Delete every transaction in ``category``; rows deleted."""

    @abstractmethod
    async def list_by_period(
        self,
        user_id: UserId,
        *,
        period_start: date,
        period_end: date,
        transaction_type: TransactionType | None = None,
        category: Category | None = None,
        card_id: CardId | None = None,
    ) -> list[Transaction]:
        """Return the transactions in the date range, newest date first.

        Capped at the service fetch limit (ample for personal-finance volumes).
        """

    @abstractmethod
    async def delete_by_card_and_period(
        self,
        user_id: UserId,
        card_id: CardId,
        *,
        period_start: date,
        period_end: date,
    ) -> int:
        """Delete a card's transactions within a period; return rows deleted."""

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
