"""Contracts (ABCs) for the recurring-transactions module."""

from abc import ABC, abstractmethod
from datetime import date, datetime

from app.shared.types import UserId

from .models import RecurringCreate, RecurringTransaction, RecurringUpdate


class RecurringRepositoryABC(ABC):
    """Contract for recurring-template persistence (data access only)."""

    @abstractmethod
    async def create(
        self, rec: RecurringCreate, user_id: UserId
    ) -> RecurringTransaction:
        """Persist a new recurring template and return it."""

    @abstractmethod
    async def get_by_id(
        self, recurring_id: str, user_id: UserId
    ) -> RecurringTransaction | None:
        """Return a template owned by ``user_id`` or ``None`` if missing."""

    @abstractmethod
    async def list_for_user(self, user_id: UserId) -> list[RecurringTransaction]:
        """Return all of a user's recurring templates, newest first."""

    @abstractmethod
    async def list_due(self, as_of: date) -> list[RecurringTransaction]:
        """Return every ACTIVE template of ALL users due on or before ``as_of``.

        This is the system job path (no ``user_id`` filter): the daily run reads
        every user's due templates to materialize them.
        """

    @abstractmethod
    async def update(
        self, recurring_id: str, user_id: UserId, data: dict[str, object]
    ) -> RecurringTransaction:
        """Apply partial updates to a template and return it."""

    @abstractmethod
    async def delete(self, recurring_id: str, user_id: UserId) -> None:
        """Delete a user's template (scoped by ``user_id``)."""


class RecurringServiceABC(ABC):
    """Contract for recurring-template use cases (business logic)."""

    @abstractmethod
    async def create_recurring(
        self, rec: RecurringCreate, user_id: UserId
    ) -> RecurringTransaction:
        """Create a recurring template, computing its first ``next_run_date``."""

    @abstractmethod
    async def list_recurring(self, user_id: UserId) -> list[RecurringTransaction]:
        """Return the user's recurring templates."""

    @abstractmethod
    async def update_recurring(
        self, recurring_id: str, user_id: UserId, data: RecurringUpdate
    ) -> RecurringTransaction:
        """Change a template's mutable fields (or raise ``RecurringNotFoundError``).

        Changing ``day_of_month`` reschedules ``next_run_date`` to the next
        occurrence of the new day.
        """

    @abstractmethod
    async def delete_recurring(
        self, recurring_id: str, user_id: UserId
    ) -> RecurringTransaction:
        """Delete a template and return it (or raise ``RecurringNotFoundError``)."""

    @abstractmethod
    async def set_active(
        self, recurring_id: str, user_id: UserId, active: bool
    ) -> RecurringTransaction:
        """Pause (``active=False``) or resume (``active=True``) a template."""

    @abstractmethod
    async def resolve_by_name(
        self, name: str, user_id: UserId
    ) -> RecurringTransaction | None:
        """Find a template by (accent-insensitive) description, or ``None``.

        Convenience wrapper over :meth:`find_matches` returning the first match;
        destructive operations should use ``find_matches`` and disambiguate.
        """

    @abstractmethod
    async def find_matches(
        self, name: str, user_id: UserId
    ) -> list[RecurringTransaction]:
        """Return EVERY template matching ``name`` (accent-insensitive).

        An exact description match short-circuits to just that template; otherwise
        all partial matches are returned so a destructive op can ask "¿cuál?" when
        more than one matches, instead of silently picking the first.
        """

    @abstractmethod
    async def run_due(self, now: datetime) -> int:
        """Materialize every due template into real transactions.

        ``now`` is a timezone-aware UTC instant. Each template is evaluated
        against ITS OWNER's local calendar day (derived from the owner's stored
        timezone), catching up occurrence-by-occurrence (bounded by
        ``MAX_CATCHUP_RUNS``) while it is active and its ``next_run_date`` is on
        or before that owner's local today. Returns the number of transactions
        created.
        """
