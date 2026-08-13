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
    async def total_paid(
        self, user_id: UserId, card_id: CardId, as_of: date | None = None
    ) -> Decimal:
        """Return the sum of payments toward ``card_id``.

        With ``as_of`` set, only payments on or before that date count (used to
        reconstruct a card's balance at a past month-end).
        """

    @abstractmethod
    async def total_paid_up_to(self, user_id: UserId, as_of: date) -> Decimal:
        """Return the sum of ALL the user's card payments made on or before ``as_of``.

        Unlike ``total_paid`` this spans every card (no ``card_id`` filter); it
        feeds the cumulative "accumulated surplus" reconstruction.
        """

    @abstractmethod
    async def list_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPayment]:
        """Return the user's card payments within the date range, newest first."""

    @abstractmethod
    async def delete(self, payment_id: str, user_id: UserId) -> None:
        """Delete a single card payment (scoped by ``user_id``)."""


class CreditCardSpendingABC(ABC):
    """Contract for computing how much was charged to a card."""

    @abstractmethod
    async def charges_summary(
        self,
        user_id: UserId,
        card_id: CardId,
        cycle_start: date,
        as_of: date,
        period: tuple[date, date] | None = None,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Return ``(total up to as_of, current-cycle total, selected-period total)``.

        All three come from a single fetch of the card's charges. ``period`` (a
        ``(start, end)`` window) drives the third figure; it is ``0`` when omitted.
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
        self,
        user_id: UserId,
        as_of: date | None = None,
        *,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> list[CreditCardStatus]:
        """Return every active card evaluated against charges, payments, cycle."""

    @abstractmethod
    async def get_status(
        self, card_id: CardId, user_id: UserId, as_of: date | None = None
    ) -> CreditCardStatus:
        """Return one card's status (or raise ``CardNotFoundError``)."""

    @abstractmethod
    async def total_paid_up_to(self, user_id: UserId, as_of: date) -> Decimal:
        """Return the sum of ALL the user's card payments on or before ``as_of``."""

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
    async def remove_payment(
        self,
        user_id: UserId,
        amount: Decimal,
        *,
        payment_date: date | None = None,
        card_id: CardId | None = None,
    ) -> CardPayment | None:
        """Delete a card payment matched by amount (and optional date/card).

        Mirrors ``GoalService.remove_contribution``: matches on ``amount`` and,
        when given, ``payment_date`` and ``card_id``; on several matches the most
        recent is removed. Returns the deleted payment, or ``None`` when nothing
        matches. This is the chat-side undo of ``register_payment``.
        """

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
