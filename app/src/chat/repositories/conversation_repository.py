"""Supabase-backed conversation/message repository (data access only)."""

from typing import Any

from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.types import UserId

from ..constants import CONVERSATIONS_TABLE, MESSAGES_TABLE
from ..interfaces import ConversationRepositoryABC
from ..models import ChatMessage

logger = get_logger(__name__)


class ConversationRepository(ConversationRepositoryABC):
    """Persists conversations and messages in Supabase."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def create_conversation(self, user_id: UserId) -> str:
        result = await self._db.insert(
            CONVERSATIONS_TABLE, {"user_id": user_id, "status": "active"}
        )
        conversation_id = str(result.data[0]["id"])
        logger.info("Conversation created", conversation_id=conversation_id, user_id=user_id)
        return conversation_id

    async def get_owner(self, conversation_id: str) -> str | None:
        result = await self._db.select(
            CONVERSATIONS_TABLE,
            QueryConfig(select="user_id", filters={"id": conversation_id}, limit=1),
        )
        if not result.data:
            return None
        return str(result.data[0]["user_id"])

    async def get_recent_messages(
        self, conversation_id: str, user_id: UserId, limit: int
    ) -> list[ChatMessage]:
        # Scope by user_id too (defense in depth): the backend key bypasses RLS.
        result = await self._db.select(
            MESSAGES_TABLE,
            QueryConfig(
                select="role,content,created_at",
                filters={"conversation_id": conversation_id, "user_id": user_id},
                order_by="created_at",
                order_ascending=False,
                limit=limit,
            ),
        )
        # Latest first from the query -> reverse to chronological order.
        messages = [_to_message(row) for row in reversed(result.data)]
        return [m for m in messages if m is not None]

    async def save_messages(
        self, conversation_id: str, user_id: UserId, messages: list[ChatMessage]
    ) -> None:
        rows = [
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "role": message.role.value,
                "content": message.content,
            }
            for message in messages
        ]
        if rows:
            await self._db.insert(MESSAGES_TABLE, rows)


def _to_message(row: dict[str, Any]) -> ChatMessage | None:
    role = row.get("role")
    content = row.get("content")
    if role not in ("user", "assistant") or not content:
        return None
    return ChatMessage(role=role, content=content)
