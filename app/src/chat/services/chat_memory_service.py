"""Conversation memory service (short-term history).

Resolves the conversation (creating one when needed, scoped to the user),
loads recent history for LLM context, and persists each turn. Persistence is
best-effort: a failure to save must never break the chat response.
"""

from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.shared.types import UserId

from ..constants import ChatRole
from ..interfaces import ChatMemoryServiceABC, ConversationRepositoryABC
from ..models import ChatMessage

logger = get_logger(__name__)


class ChatMemoryService(ChatMemoryServiceABC):
    """Short-term conversation memory backed by the conversation repository."""

    def __init__(self, repository: ConversationRepositoryABC) -> None:
        self._repository = repository

    async def resolve_conversation(self, user_id: UserId, session_id: str | None) -> str:
        """Return the user's conversation for ``session_id`` or create a new one.

        A ``session_id`` is only reused if it is a valid conversation owned by
        the same user (isolation); otherwise a fresh conversation is created.
        """
        if session_id and _is_uuid(session_id):
            owner = await self._repository.get_owner(session_id)
            if owner == user_id:
                return session_id

        return await self._repository.create_conversation(user_id)

    async def load_history(self, conversation_id: str, user_id: UserId) -> list[ChatMessage]:
        return await self._repository.get_recent_messages(
            conversation_id, user_id, limit=settings.CHAT_HISTORY_LIMIT
        )

    async def save_turn(
        self, conversation_id: str, user_id: UserId, user_message: str, assistant_message: str
    ) -> None:
        try:
            await self._repository.save_messages(
                conversation_id,
                user_id,
                [
                    ChatMessage(role=ChatRole.USER, content=user_message),
                    ChatMessage(role=ChatRole.ASSISTANT, content=assistant_message),
                ],
            )
        except Exception as e:  # noqa: BLE001 - persistence is best-effort.
            logger.error("Failed to persist conversation turn", error=str(e))


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False
