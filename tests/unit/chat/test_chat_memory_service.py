"""Unit tests for the chat memory service (repository mocked)."""

from app.src.chat.interfaces import ConversationRepositoryABC
from app.src.chat.models import ChatMessage
from app.src.chat.services.chat_memory_service import ChatMemoryService

VALID_UUID = "11111111-1111-1111-1111-111111111111"


class FakeConversationRepository(ConversationRepositoryABC):
    def __init__(self, owner: str | None = None, messages: list[ChatMessage] | None = None) -> None:
        self.owner = owner
        self.messages = messages or []
        self.created_for: list[str] = []
        self.saved: list[tuple[str, list[ChatMessage]]] = []
        self.recent_calls: list[tuple[str, str]] = []
        self.raise_on_save = False

    async def create_conversation(self, user_id: str) -> str:
        self.created_for.append(user_id)
        return "new-conversation-id"

    async def get_owner(self, conversation_id: str) -> str | None:
        return self.owner

    async def get_recent_messages(
        self, conversation_id: str, user_id: str, limit: int
    ) -> list[ChatMessage]:
        self.recent_calls.append((conversation_id, user_id))
        return self.messages

    async def save_messages(self, conversation_id, user_id, messages) -> None:  # type: ignore[no-untyped-def]
        if self.raise_on_save:
            raise RuntimeError("db down")
        self.saved.append((conversation_id, messages))


class TestResolveConversation:
    async def test_reuses_conversation_owned_by_user(self) -> None:
        repo = FakeConversationRepository(owner="u1")
        service = ChatMemoryService(repo)

        result = await service.resolve_conversation("u1", VALID_UUID)

        assert result == VALID_UUID
        assert repo.created_for == []  # not created

    async def test_creates_new_when_not_owner(self) -> None:
        repo = FakeConversationRepository(owner="someone-else")
        service = ChatMemoryService(repo)

        result = await service.resolve_conversation("u1", VALID_UUID)

        assert result == "new-conversation-id"
        assert repo.created_for == ["u1"]

    async def test_creates_new_when_no_session(self) -> None:
        repo = FakeConversationRepository()
        result = await ChatMemoryService(repo).resolve_conversation("u1", None)
        assert result == "new-conversation-id"

    async def test_invalid_session_id_creates_new(self) -> None:
        repo = FakeConversationRepository(owner="u1")
        result = await ChatMemoryService(repo).resolve_conversation("u1", "not-a-uuid")
        assert result == "new-conversation-id"


class TestSaveTurn:
    async def test_saves_user_and_assistant(self) -> None:
        repo = FakeConversationRepository()
        service = ChatMemoryService(repo)

        await service.save_turn("conv-1", "u1", "gasté 50", "Registré tu gasto")

        _, messages = repo.saved[0]
        assert [(m.role, m.content) for m in messages] == [
            ("user", "gasté 50"),
            ("assistant", "Registré tu gasto"),
        ]

    async def test_never_raises_on_repo_error(self) -> None:
        repo = FakeConversationRepository()
        repo.raise_on_save = True
        # Should not raise (best-effort persistence).
        await ChatMemoryService(repo).save_turn("conv-1", "u1", "a", "b")


class TestLoadHistory:
    async def test_delegates_and_scopes_to_user(self) -> None:
        repo = FakeConversationRepository(messages=[ChatMessage(role="user", content="hola")])
        result = await ChatMemoryService(repo).load_history("conv-1", "u1")
        assert [m.content for m in result] == ["hola"]
        assert repo.recent_calls == [("conv-1", "u1")]  # user_id is passed through
