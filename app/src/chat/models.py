"""Domain models for the chat memory module."""

from pydantic import BaseModel

from .constants import ChatRole


class ChatMessage(BaseModel):
    """A single stored conversation message."""

    role: ChatRole
    content: str
