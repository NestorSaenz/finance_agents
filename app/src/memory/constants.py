"""Static values for the long-term memory (Memory Agent) module."""

from typing import Final

USER_KNOWLEDGE_TABLE: Final[str] = "user_knowledge"
ON_CONFLICT: Final[str] = "user_id,key"

# Cap how many facts we keep / extract per turn (keeps prompts + storage bounded).
MAX_KNOWLEDGE_ENTRIES: Final[int] = 30
MAX_ENTRIES_PER_TURN: Final[int] = 5
