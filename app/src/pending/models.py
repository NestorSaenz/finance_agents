"""Domain models for the pending-actions module."""

from datetime import datetime

from pydantic import BaseModel

from .types import PendingActionKind


class PendingAction(BaseModel):
    """A proposal waiting for the user's confirmation in a LATER turn.

    One row per ``(user_id, conversation_id)``; ``turn_id`` is the turn that made
    the proposal, so the same turn can never confirm it.
    """

    user_id: str
    conversation_id: str
    kind: PendingActionKind
    payload: dict[str, object]
    turn_id: str
    created_at: datetime
    expires_at: datetime
