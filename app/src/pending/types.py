"""Enumerations for the pending-actions module."""

from enum import StrEnum


class PendingActionKind(StrEnum):
    """Kinds of action that wait for the user's confirmation in a later turn."""

    CARD_SCHEDULE = "card_schedule"
