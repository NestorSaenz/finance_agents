"""Domain models for the rate-limiting module."""

from enum import StrEnum


class RateLimitBucket(StrEnum):
    """A counter window a chat turn can consume.

    - ``CHAT_MINUTE``: burst guard, every turn (text or image) consumes it.
    - ``CHAT_DAY``: daily allowance for text turns.
    - ``IMAGE_DAY``: daily allowance for image turns (heavier: Gemini vision).
    """

    CHAT_MINUTE = "chat_minute"
    CHAT_DAY = "chat_day"
    IMAGE_DAY = "image_day"
