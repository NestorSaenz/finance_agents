"""Contracts (ABCs) for the pending-actions module."""

from abc import ABC, abstractmethod

from app.shared.turn import TurnContext
from app.shared.types import ConversationId, UserId

from .models import PendingAction
from .types import PendingActionKind


class PendingActionRepositoryABC(ABC):
    """Contract for pending-action persistence (data access only)."""

    @abstractmethod
    async def upsert(self, action: PendingAction) -> None:
        """Store ``action``, replacing the user's pending row for that conversation."""

    @abstractmethod
    async def get(
        self, user_id: UserId, conversation_id: ConversationId
    ) -> PendingAction | None:
        """Return the user's pending row for the conversation (expired or not), if any."""

    @abstractmethod
    async def consume(
        self,
        user_id: UserId,
        conversation_id: ConversationId,
        kind: PendingActionKind,
        turn_id: str,
    ) -> dict[str, object] | None:
        """Atomically delete and return the payload of a matching live proposal.

        Matches only a row of this user/conversation/kind that is NOT expired and
        was proposed in a turn OTHER than ``turn_id``. Returns ``None`` otherwise.
        """

    @abstractmethod
    async def discard_stale(
        self, user_id: UserId, conversation_id: ConversationId, keep_turn_id: str
    ) -> None:
        """Delete the user's expired rows and this conversation's rows of other turns."""


class PendingActionServiceABC(ABC):
    """Contract for the propose-now / confirm-later use cases."""

    @abstractmethod
    async def propose(
        self,
        user_id: UserId,
        turn: TurnContext,
        kind: PendingActionKind,
        payload: dict[str, object],
    ) -> bool:
        """Record a proposal made in ``turn`` (replaces any earlier one).

        Returns ``False`` (storing nothing) when a live proposal of the same kind and
        IDENTICAL payload from an EARLIER turn is already pending, so re-proposing the
        same thing in the confirming turn cannot reset it. Otherwise returns ``True``.
        """

    @abstractmethod
    async def consume(
        self, user_id: UserId, turn: TurnContext, kind: PendingActionKind
    ) -> dict[str, object] | None:
        """Return (once) the payload proposed in an EARLIER turn, else ``None``."""

    @abstractmethod
    async def discard_stale(
        self, user_id: UserId, turn: TurnContext, *, keep_current: bool = True
    ) -> None:
        """Drop expired proposals and those made before ``turn`` (end-of-turn sweep).

        With ``keep_current=False`` the conversation's proposals are dropped too, even
        this turn's: used when the turn failed and the user never saw its proposal.
        """
