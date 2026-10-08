"""Propose-now / confirm-later orchestration (owns the proposal TTL)."""

from datetime import UTC, datetime

from app.shared.turn import TurnContext
from app.shared.types import UserId

from ..constants import PENDING_ACTION_TTL
from ..interfaces import PendingActionRepositoryABC, PendingActionServiceABC
from ..models import PendingAction
from ..types import PendingActionKind


class PendingActionService(PendingActionServiceABC):
    """Stores proposals with a TTL and releases each one at most once, in a later turn."""

    def __init__(self, repository: PendingActionRepositoryABC) -> None:
        self._repository = repository

    async def propose(
        self,
        user_id: UserId,
        turn: TurnContext,
        kind: PendingActionKind,
        payload: dict[str, object],
    ) -> bool:
        now = datetime.now(UTC)
        # Read-then-write (the DatabaseInterface has no conditional upsert). The tiny
        # race (two instances proposing for the same conversation at once) is benign:
        # worst case the later write wins and the proposal is re-asked.
        existing = await self._repository.get(user_id, turn.conversation_id)
        if (
            existing is not None
            and existing.kind == kind
            and existing.payload == payload
            and existing.turn_id != turn.turn_id
            and existing.expires_at >= now
        ):
            return False
        await self._repository.upsert(
            PendingAction(
                user_id=user_id,
                conversation_id=turn.conversation_id,
                kind=kind,
                payload=payload,
                turn_id=turn.turn_id,
                created_at=now,
                expires_at=now + PENDING_ACTION_TTL,
            )
        )
        return True

    async def consume(
        self, user_id: UserId, turn: TurnContext, kind: PendingActionKind
    ) -> dict[str, object] | None:
        return await self._repository.consume(user_id, turn.conversation_id, kind, turn.turn_id)

    async def discard_stale(
        self, user_id: UserId, turn: TurnContext, *, keep_current: bool = True
    ) -> None:
        # An empty keep id matches no stored turn, so every row of the conversation goes.
        keep_turn_id = turn.turn_id if keep_current else ""
        await self._repository.discard_stale(user_id, turn.conversation_id, keep_turn_id)
