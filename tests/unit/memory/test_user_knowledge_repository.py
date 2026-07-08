"""Unit tests for the user-knowledge repository (data access only)."""

from app.src.memory.constants import (
    MAX_KNOWLEDGE_ENTRIES,
    ON_CONFLICT,
    USER_KNOWLEDGE_TABLE,
)
from app.src.memory.models import KnowledgeEntry
from app.src.memory.repositories.user_knowledge_repository import (
    UserKnowledgeRepository,
)
from tests.fakes import FakeDatabase


class TestGetAll:
    async def test_maps_rows_to_entries(self) -> None:
        db = FakeDatabase(
            rows=[
                {"key": "moneda_preferida", "value": "MXN"},
                {"key": "meta_ahorro", "value": "viaje a Japón"},
            ]
        )
        repo = UserKnowledgeRepository(db)

        entries = await repo.get_all("u1")

        assert entries == [
            KnowledgeEntry(key="moneda_preferida", value="MXN"),
            KnowledgeEntry(key="meta_ahorro", value="viaje a Japón"),
        ]

    async def test_scopes_query_to_user_and_caps_results(self) -> None:
        db = FakeDatabase(rows=[])
        repo = UserKnowledgeRepository(db)

        await repo.get_all("u1")

        config = db.select_configs[0]
        assert config is not None
        assert config.filters == {"user_id": "u1"}
        assert config.limit == MAX_KNOWLEDGE_ENTRIES

    async def test_skips_rows_missing_key_or_value(self) -> None:
        db = FakeDatabase(
            rows=[
                {"key": "moneda", "value": "MXN"},
                {"key": "", "value": "x"},
                {"key": "meta", "value": ""},
            ]
        )
        repo = UserKnowledgeRepository(db)

        entries = await repo.get_all("u1")

        assert entries == [KnowledgeEntry(key="moneda", value="MXN")]


class TestUpsertMany:
    async def test_writes_rows_with_user_id_and_conflict_target(self) -> None:
        db = FakeDatabase()
        repo = UserKnowledgeRepository(db)

        await repo.upsert_many(
            "u1",
            [
                KnowledgeEntry(key="moneda", value="MXN"),
                KnowledgeEntry(key="meta", value="ahorrar"),
            ],
        )

        assert db.upserted == [
            {"user_id": "u1", "key": "moneda", "value": "MXN"},
            {"user_id": "u1", "key": "meta", "value": "ahorrar"},
        ]
        table, on_conflict = db.upsert_calls[0]
        assert table == USER_KNOWLEDGE_TABLE
        assert on_conflict == ON_CONFLICT

    async def test_no_write_when_empty(self) -> None:
        db = FakeDatabase()
        repo = UserKnowledgeRepository(db)

        await repo.upsert_many("u1", [])

        assert db.upserted == []
