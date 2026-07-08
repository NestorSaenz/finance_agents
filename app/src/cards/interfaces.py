"""Contracts (ABCs) for the credit-cards module."""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal

from app.shared.types import CardId, UserId

from .models import (
    CardPayment,
    CardPaymentCreate,
    CardPaymentView,
    CreditCard,
    CreditCardCreate,
    CreditCardStatus,
)


class CreditCardRepositoryABC(ABC):
    """Contract for credit-card persistence (data access only)."""

    @abstractmethod
    async def create(self, card: CreditCardCreate, user_id: UserId) -> CreditCard:
        """Persist a new credit card and return it."""

    @abstractmethod
    async def get_by_id(self, card_id: CardId, user_id: UserId) -> CreditCard | None:
        """Return a card owned by ``user_id`` or ``None`` if missing."""

    @abstractmethod
    async def list_active(self, user_id: UserId) -> list[CreditCard]:
        """Return all active cards for a user."""

    @abstractmethod
    async def update(
        self,
        card_id: CardId,
        user_id: UserId,
        *,
        name: str | None = None,
        credit_limit: Decimal | None = None,
        cutoff_day: int | None = None,
        payment_day: int | None = None,
    ) -> CreditCard | None:
        """Update a card's mutable fields; return it, or ``None`` if missing."""

    @abstractmethod
    async def deactivate(self, card_id: CardId, user_id: UserId) -> CreditCard | None:
        """Soft-delete a card (``is_active=False``), preserving its charges/payments."""


class CardPaymentRepositoryABC(ABC):
    """Contract for credit-card payment persistence (data access only)."""

    @abstractmethod
    async def create(
        self, payment: CardPaymentCreate, card_id: CardId, user_id: UserId
    ) -> CardPayment:
        """Persist a payment toward a card and return it."""

    @abstractmethod
    async def total_paid(self, user_id: UserId, card_id: CardId) -> Decimal:
        """Return the sum of all payments made toward ``card_id``."""

    @abstractmethod
    async def list_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPayment]:
        """Return the user's card payments within the date range, newest first."""


class CreditCardSpendingABC(ABC):
    """Contract for computing how much was charged to a card."""

    @abstractmethod
    async def charges_summary(
        self, user_id: UserId, card_id: CardId, cycle_start: date, as_of: date
    ) -> tuple[Decimal, Decimal]:
        """Return ``(total charged up to as_of, charged within the cycle)``.

        Both figures come from a single fetch of the card's charges to avoid
        querying the same rows twice.
        """


class CreditCardServiceABC(ABC):
    """Contract for credit-card use cases (business logic)."""

    @abstractmethod
    async def create_card(self, card: CreditCardCreate, user_id: UserId) -> CreditCard:
        """Register a credit card."""

    @abstractmethod
    async def list_cards(self, user_id: UserId) -> list[CreditCard]:
        """Return the user's active cards."""

    @abstractmethod
    async def get_all_status(
        self, user_id: UserId, as_of: date | None = None
    ) -> list[CreditCardStatus]:
        """Return every active card evaluated against charges, payments, cycle."""

    @abstractmethod
    async def get_status(
        self, card_id: CardId, user_id: UserId, as_of: date | None = None
    ) -> CreditCardStatus:
        """Return one card's status (or raise ``CardNotFoundError``)."""

    @abstractmethod
    async def register_payment(
        self, card_id: CardId, user_id: UserId, payment: CardPaymentCreate
    ) -> CardPayment:
        """Record a payment toward a card (or raise if the card is missing)."""

    @abstractmethod
    async def list_payments(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPaymentView]:
        """Return the user's card payments in the period, with card names."""

    @abstractmethod
    async def resolve_by_name(self, name: str, user_id: UserId) -> CreditCard | None:
        """Find a card by (fuzzy) name so charges/payments can link to it."""

    @abstractmethod
    async def update_card(
        self,
        card_id: CardId,
        user_id: UserId,
        *,
        name: str | None = None,
        credit_limit: Decimal | None = None,
        cutoff_day: int | None = None,
        payment_day: int | None = None,
    ) -> CreditCard:
        """Change a card's details or raise ``CardNotFoundError``."""

    @abstractmethod
    async def delete_card(self, card_id: CardId, user_id: UserId) -> CreditCard:
        """Deactivate a card (soft delete) or raise ``CardNotFoundError``."""
