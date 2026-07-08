"""pgvector-backed vector store (Supabase/Postgres).

Implements ``VectorStoreInterface`` using a ``vector_embeddings`` table and a
``match_vectors`` SQL function (see database/migrations/003_pgvector.sql).
Similarity search runs through an RPC because PostgREST cannot express the
``<=>`` operator directly.
"""

from typing import Any

from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.interfaces.vector_store import (
    SearchConfig,
    SearchResult,
    VectorRecord,
    VectorStoreInterface,
)

logger = get_logger(__name__)

VECTOR_TABLE = "vector_embeddings"
MATCH_FUNCTION = "match_vectors"


class PgVectorStore(VectorStoreInterface):
    """Vector store backed by Postgres + pgvector via Supabase."""

    def __init__(self, db: DatabaseInterface, dimensions: int) -> None:
        self._db = db
        self._dimensions = dimensions

    async def upsert(self, records: list[VectorRecord], namespace: str | None = None) -> int:
        rows = [
            {
                "id": record.id,
                "namespace": namespace or "",
                "embedding": record.vector,
                "metadata": record.metadata,
            }
            for record in records
        ]
        if not rows:
            return 0
        await self._db.insert(VECTOR_TABLE, rows)
        return len(rows)

    async def search(
        self, vector: list[float], config: SearchConfig | None = None
    ) -> list[SearchResult]:
        config = config or SearchConfig()
        result = await self._db.execute_rpc(
            MATCH_FUNCTION,
            {
                "query_embedding": vector,
                "match_namespace": config.namespace or "",
                "match_count": config.top_k,
                "metadata_filter": config.filter or {},
            },
        )
        return [
            SearchResult(
                id=str(row.get("id", "")),
                score=float(row.get("similarity", 0.0)),
                metadata=row.get("metadata") or {},
            )
            for row in result.data
        ]

    async def delete(self, ids: list[str], namespace: str | None = None) -> int:
        deleted = 0
        for vector_id in ids:
            await self._db.delete(VECTOR_TABLE, {"id": vector_id})
            deleted += 1
        return deleted

    async def delete_by_filter(
        self, filter: dict[str, Any], namespace: str | None = None
    ) -> int:
        # Clearing a whole namespace is the supported case (used for re-seeding).
        filters: dict[str, Any] = {}
        if namespace is not None:
            filters["namespace"] = namespace
        if not filters:
            logger.warning("delete_by_filter without namespace is a no-op for pgvector store")
            return 0
        result = await self._db.delete(VECTOR_TABLE, filters)
        return len(result.data)

    async def fetch(self, ids: list[str], namespace: str | None = None) -> list[VectorRecord]:
        records: list[VectorRecord] = []
        for vector_id in ids:
            result = await self._db.select(
                VECTOR_TABLE, QueryConfig(filters={"id": vector_id}, limit=1)
            )
            if result.data:
                row = result.data[0]
                records.append(
                    VectorRecord(
                        id=str(row["id"]),
                        vector=row.get("embedding", []),
                        metadata=row.get("metadata") or {},
                    )
                )
        return records

    async def get_stats(self) -> dict[str, Any]:
        result = await self._db.select(VECTOR_TABLE, QueryConfig(select="id"))
        return {"total_vector_count": len(result.data), "dimensions": self._dimensions}

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def provider(self) -> str:
        return "pgvector"
