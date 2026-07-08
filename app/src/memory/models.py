"""Domain models for the memory module."""

from pydantic import BaseModel


class KnowledgeEntry(BaseModel):
    """A durable fact about the user (key/value)."""

    key: str
    value: str
