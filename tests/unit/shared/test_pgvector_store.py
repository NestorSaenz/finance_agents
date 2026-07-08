"""Unit tests for the pgvector store (database mocked via RPC)."""

from app.shared.clients.pgvector_store import MATCH_FUNCTION, PgVectorStore
from app.shared.interfaces.vector_store import SearchConfig, VectorRecord
from tests.fakes import FakeDatabase


class TestUpsert:
    async def test_inserts_rows_with_namespace_and_metadata(self) -> None:
        db = FakeDatabase()
        store = PgVectorStore(db, dimensions=768)

        count = await store.upsert(
            [VectorRecord(id="v1", vector=[0.1] * 768, metadata={"category": "restaurantes"})],
            namespace="categories",
        )

        assert count == 1
        row = db.inserted[0]
        assert row["id"] == "v1"
        assert row["namespace"] == "categories"
        assert row["metadata"] == {"category": "restaurantes"}
        assert len(row["embedding"]) == 768

    async def test_empty_upsert_is_noop(self) -> None:
        db = FakeDatabase()
        store = PgVectorStore(db, dimensions=768)
        assert await store.upsert([], namespace="categories") == 0
        assert db.inserted == []


class TestSearch:
    async def test_calls_match_rpc_and_maps_results(self) -> None:
        db = FakeDatabase()
        db.rpc_result = [
            {"id": "v1", "similarity": 0.91, "metadata": {"category": "restaurantes"}},
            {"id": "v2", "similarity": 0.40, "metadata": {"category": "transporte"}},
        ]
        store = PgVectorStore(db, dimensions=768)

        results = await store.search(
            [0.1] * 768,
            SearchConfig(top_k=5, namespace="categories", filter={"user_id": "u1"}),
        )

        fn, params = db.rpc_calls[-1]
        assert fn == MATCH_FUNCTION
        assert params["match_namespace"] == "categories"
        assert params["match_count"] == 5
        assert params["metadata_filter"] == {"user_id": "u1"}

        assert len(results) == 2
        assert results[0].id == "v1"
        assert results[0].score == 0.91
        assert results[0].metadata["category"] == "restaurantes"

    async def test_empty_results(self) -> None:
        store = PgVectorStore(FakeDatabase(), dimensions=768)
        results = await store.search([0.1] * 768, SearchConfig(namespace="categories"))
        assert results == []


class TestDeleteAndStats:
    async def test_delete_by_filter_clears_namespace(self) -> None:
        db = FakeDatabase(rows=[{"id": "v1"}])
        store = PgVectorStore(db, dimensions=768)

        await store.delete_by_filter(filter={"type": "category_example"}, namespace="categories")

        assert db.deleted[-1] == {"namespace": "categories"}

    async def test_delete_by_filter_without_namespace_is_noop(self) -> None:
        db = FakeDatabase()
        store = PgVectorStore(db, dimensions=768)
        assert await store.delete_by_filter(filter={}, namespace=None) == 0
        assert db.deleted == []

    async def test_provider_and_stats(self) -> None:
        db = FakeDatabase(rows=[{"id": "v1"}, {"id": "v2"}])
        store = PgVectorStore(db, dimensions=768)

        assert store.provider == "pgvector"
        assert store.dimensions == 768
        stats = await store.get_stats()
        assert stats["total_vector_count"] == 2
