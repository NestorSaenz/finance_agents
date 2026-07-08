"""Supabase-backed user-knowledge repository (data access only)."""

from typing import Any

from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.types import UserId

from ..constants import MAX_KNOWLEDGE_ENTRIES, ON_CONFLICT, USER_KNOWLEDGE_TABLE
from ..interfaces import UserKnowledgeRepositoryABC
from ..models import KnowledgeEntry

logger = get_logger(__name__)


class UserKnowledgeRepository(UserKnowledgeRepositoryABC):
    """Persists the user's long-term knowledge facts in Supabase."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def get_all(self, user_id: UserId) -> list[KnowledgeEntry]:
        result = await self._db.select(
            USER_KNOWLEDGE_TABLE,
            QueryConfig(
                select="key,value",
                filters={"user_id": user_id},
                order_by="updated_at",
                order_ascending=False,
                limit=MAX_KNOWLEDGE_ENTRIES,
            ),
        )
        entries = [_to_entry(row) for row in result.data]
        return [entry for entry in entries if entry is not None]

    async def upsert_many(self, user_id: UserId, entries: list[KnowledgeEntry]) -> None:
        rows = [
            {"user_id": user_id, "key": entry.key, "value": entry.value}
            for entry in entries
        ]
        if rows:
            await self._db.upsert(USER_KNOWLEDGE_TABLE, rows, on_conflict=ON_CONFLICT)


def _to_entry(row: dict[str, Any]) -> KnowledgeEntry | None:
    key = row.get("key")
    value = row.get("value")
    if not key or not value:
        return None
    return KnowledgeEntry(key=str(key), value=str(value))
