"""Static values for the chat memory module."""

from enum import Enum
from typing import Final

CONVERSATIONS_TABLE: Final[str] = "conversations"
MESSAGES_TABLE: Final[str] = "messages"


class ChatRole(str, Enum):
    """Role of a stored conversation message."""

    USER = "user"
    ASSISTANT = "assistant"
