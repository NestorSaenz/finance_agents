"""Static values for the pending-actions module."""

from datetime import timedelta
from typing import Final

# How long a proposal stays confirmable. It is also only valid in the very next
# user turn (the route sweeps older ones), so this is an upper bound.
PENDING_ACTION_TTL: Final[timedelta] = timedelta(minutes=10)

PENDING_ACTIONS_TABLE: Final[str] = "pending_actions"
PENDING_ACTIONS_CONFLICT_COLUMNS: Final[str] = "user_id,conversation_id"

# Supabase functions (migration 016). Consuming/discarding must be atomic and
# multi-instance safe, so they live in SQL rather than in select-then-delete.
CONSUME_PENDING_ACTION_RPC: Final[str] = "consume_pending_action"
DISCARD_STALE_PENDING_ACTIONS_RPC: Final[str] = "discard_stale_pending_actions"
