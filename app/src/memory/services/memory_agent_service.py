"""Memory Agent service: extracts durable user facts and serves them as context.

Runs as a best-effort, fire-and-forget step after each chat turn: it never
raises (a memory failure must not affect the conversation).
"""

import json

from app.core.logging import get_logger
from app.shared.interfaces.llm import LLMConfig, LLMInterface, Message, MessageRole
from app.shared.types import UserId

from ..constants import MAX_ENTRIES_PER_TURN
from ..interfaces import MemoryAgentServiceABC, UserKnowledgeRepositoryABC
from ..models import KnowledgeEntry
from ..prompts import MEMORY_EXTRACTION_PROMPT, MEMORY_SYSTEM_PROMPT

logger = get_logger(__name__)


class MemoryAgentService(MemoryAgentServiceABC):
    """Extracts and stores long-term user knowledge from conversations."""

    def __init__(self, repository: UserKnowledgeRepositoryABC, llm: LLMInterface) -> None:
        self._repository = repository
        self._llm = llm

    async def process(
        self, user_id: UserId, user_message: str, assistant_message: str
    ) -> None:
        try:
            existing = await self._repository.get_all(user_id)
            entries = await self._extract(user_message, assistant_message, existing)
            if entries:
                await self._repository.upsert_many(user_id, entries)
                logger.info("User knowledge updated", user_id=user_id, count=len(entries))
        except Exception as e:  # noqa: BLE001 - memory is best-effort; never break the turn.
            logger.error("Memory agent failed", error=str(e))

    async def get_context(self, user_id: UserId) -> str:
        try:
            entries = await self._repository.get_all(user_id)
        except Exception as e:  # noqa: BLE001 - context is optional.
            logger.error("Failed to load user knowledge", error=str(e))
            return ""
        return "\n".join(f"- {entry.key}: {entry.value}" for entry in entries)

    async def _extract(
        self, user_message: str, assistant_message: str, existing: list[KnowledgeEntry]
    ) -> list[KnowledgeEntry]:
        prompt = MEMORY_EXTRACTION_PROMPT.format(
            existing=_format_existing(existing),
            user_message=user_message,
            assistant_message=assistant_message,
        )
        config = LLMConfig(temperature=0.1, max_tokens=400)
        response = await self._llm.generate(
            [
                Message(role=MessageRole.SYSTEM, content=MEMORY_SYSTEM_PROMPT),
                Message(role=MessageRole.USER, content=prompt),
            ],
            config,
        )
        return _parse_entries(response.content)


def _format_existing(existing: list[KnowledgeEntry]) -> str:
    if not existing:
        return "  (ninguna)"
    return "\n".join(f"  - {entry.key}: {entry.value}" for entry in existing)


def _parse_entries(content: str) -> list[KnowledgeEntry]:
    """Parse the LLM's JSON into knowledge entries (tolerant, capped)."""
    text = content.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:-1])

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Memory extraction returned invalid JSON")
        return []

    raw = data.get("knowledge", []) if isinstance(data, dict) else []
    entries: list[KnowledgeEntry] = []
    for item in raw:
        if isinstance(item, dict) and item.get("key") and item.get("value"):
            entries.append(KnowledgeEntry(key=str(item["key"]), value=str(item["value"])))
    return entries[:MAX_ENTRIES_PER_TURN]
