"""Unit tests for the conversation repository (DB mocked)."""

from app.src.chat.repositories.conversation_repository import ConversationRepository
from tests.fakes import FakeDatabase


class TestCreateConversation:
    async def test_inserts_and_returns_id(self) -> None:
        db = FakeDatabase()
        repo = ConversationRepository(db)

        conversation_id = await repo.create_conversation("u1")

        assert db.inserted[0]["user_id"] == "u1"
        assert db.inserted[0]["status"] == "active"
        assert conversation_id  # an id was returned


class TestGetOwner:
    async def test_returns_owner(self) -> None:
        repo = ConversationRepository(FakeDatabase(rows=[{"user_id": "u1"}]))
        assert await repo.get_owner("conv-1") == "u1"

    async def test_returns_none_when_missing(self) -> None:
        repo = ConversationRepository(FakeDatabase(rows=[]))
        assert await repo.get_owner("conv-1") is None


class TestGetRecentMessages:
    async def test_reverses_to_chronological_and_filters_system(self) -> None:
        # DB returns latest-first (order desc).
        db = FakeDatabase(
            rows=[
                {"role": "assistant", "content": "b2"},
                {"role": "user", "content": "a2"},
                {"role": "system", "content": "sys"},  # filtered out
                {"role": "assistant", "content": "b1"},
            ]
        )
        repo = ConversationRepository(db)

        messages = await repo.get_recent_messages("conv-1", "u1", limit=10)

        # Reversed to chronological, system dropped.
        assert [(m.role, m.content) for m in messages] == [
            ("assistant", "b1"),
            ("user", "a2"),
            ("assistant", "b2"),
        ]
        assert db.select_configs[-1].limit == 10


class TestSaveMessages:
    async def test_inserts_rows(self) -> None:
        from app.src.chat.models import ChatMessage

        db = FakeDatabase()
        repo = ConversationRepository(db)

        await repo.save_messages(
            "conv-1",
            "u1",
            [ChatMessage(role="user", content="hola"), ChatMessage(role="assistant", content="hey")],
        )

        assert len(db.inserted) == 2
        assert db.inserted[0] == {
            "conversation_id": "conv-1",
            "user_id": "u1",
            "role": "user",
            "content": "hola",
            "id": db.inserted[0]["id"],
            "created_at": db.inserted[0]["created_at"],
        }

    async def test_empty_is_noop(self) -> None:
        db = FakeDatabase()
        await ConversationRepository(db).save_messages("conv-1", "u1", [])
        assert db.inserted == []
