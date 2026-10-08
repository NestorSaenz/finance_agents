"""Supabase-backed pending-action store (data access only)."""

from collections.abc import Sequence
from typing import Any

import httpx
from postgrest.exceptions import APIError

from app.core.exceptions import DatabaseQueryError
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.types import ConversationId, UserId

from ..constants import (
    CONSUME_PENDING_ACTION_RPC,
    DISCARD_STALE_PENDING_ACTIONS_RPC,
    PENDING_ACTIONS_CONFLICT_COLUMNS,
    PENDING_ACTIONS_TABLE,
)
from ..interfaces import PendingActionRepositoryABC
from ..models import PendingAction
from ..types import PendingActionKind

# Raw failures the Supabase/PostgREST client can raise; wrapped as DatabaseQueryError.
_DB_FAILURES = (APIError, httpx.HTTPError)


class PendingActionRepository(PendingActionRepositoryABC):
    """Stores proposals; consume/discard go through atomic RPCs (migration 016)."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def upsert(self, action: PendingAction) -> None:
        row: dict[str, Any] = {
            "user_id": action.user_id,
            "conversation_id": action.conversation_id,
            "kind": action.kind.value,
            "payload": action.payload,
            "turn_id": action.turn_id,
            "created_at": action.created_at.isoformat(),
            "expires_at": action.expires_at.isoformat(),
        }
        try:
            await self._db.upsert(
                PENDING_ACTIONS_TABLE, row, on_conflict=PENDING_ACTIONS_CONFLICT_COLUMNS
            )
        except _DB_FAILURES as e:
            raise DatabaseQueryError("upsert pending action", str(e)) from e

    async def get(
        self, user_id: UserId, conversation_id: ConversationId
    ) -> PendingAction | None:
        try:
            result = await self._db.select(
                PENDING_ACTIONS_TABLE,
                QueryConfig(
                    filters={"user_id": user_id, "conversation_id": conversation_id}, limit=1
                ),
            )
        except _DB_FAILURES as e:
            raise DatabaseQueryError("select pending action", str(e)) from e
        return PendingAction.model_validate(result.data[0]) if result.data else None

    async def consume(
        self,
        user_id: UserId,
        conversation_id: ConversationId,
        kind: PendingActionKind,
        turn_id: str,
    ) -> dict[str, object] | None:
        try:
            result = await self._db.execute_rpc(
                CONSUME_PENDING_ACTION_RPC,
                {
                    "p_user_id": user_id,
                    "p_conversation_id": conversation_id,
                    "p_kind": kind.value,
                    "p_turn_id": turn_id,
                },
            )
        except _DB_FAILURES as e:
            raise DatabaseQueryError("consume pending action", str(e)) from e
        return _parse_payload(result.data)

    async def discard_stale(
        self, user_id: UserId, conversation_id: ConversationId, keep_turn_id: str
    ) -> None:
        try:
            await self._db.execute_rpc(
                DISCARD_STALE_PENDING_ACTIONS_RPC,
                {
                    "p_user_id": user_id,
                    "p_conversation_id": conversation_id,
                    "p_keep_turn_id": keep_turn_id,
                },
            )
        except _DB_FAILURES as e:
            raise DatabaseQueryError("discard stale pending actions", str(e)) from e


def _parse_payload(data: Sequence[object]) -> dict[str, object] | None:
    """Return the JSONB payload from ``consume_pending_action``, or ``None`` when empty."""
    value: object = data[0] if data else None
    if not isinstance(value, dict):
        return None
    return {str(k): v for k, v in value.items()}
