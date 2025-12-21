"""Pinecone Vector Store - Implementation of VectorStoreInterface for Pinecone.

Uses Pinecone Serverless for vector storage and similarity search.
"""

from typing import Any

from pinecone import Pinecone

from app.core.logging import get_logger
from app.shared.interfaces.vector_store import (
    SearchConfig,
    SearchResult,
    VectorRecord,
    VectorStoreInterface,
)

logger = get_logger(__name__)


class PineconeVectorStore(VectorStoreInterface):
    """Pinecone implementation of VectorStoreInterface.

    Uses Pinecone Serverless for efficient vector storage and search.
    Supports namespaces for multi-tenant isolation.
    """

    def __init__(
        self,
        api_key: str,
        index_name: str,
        dimensions: int = 1024,
    ) -> None:
        """Initialize the Pinecone vector store.

        Args:
            api_key: Pinecone API key.
            index_name: Name of the Pinecone index.
            dimensions: Vector dimensions (default: 1024 for Cohere Embed v3).
        """
        self._client = Pinecone(api_key=api_key)
        self._index = self._client.Index(index_name)
        self._index_name = index_name
        self._dimensions = dimensions
        logger.info("Pinecone vector store initialized", index=index_name)

    async def upsert(
        self,
        records: list[VectorRecord],
        namespace: str | None = None,
    ) -> int:
        """Insert or update vectors in Pinecone.

        Args:
            records: List of vector records to upsert.
            namespace: Optional namespace for multi-tenancy.

        Returns:
            Number of vectors upserted.
        """
        vectors = [
            {
                "id": record.id,
                "values": record.vector,
                "metadata": record.metadata,
            }
            for record in records
        ]

        logger.info(
            "Upserting vectors",
            count=len(vectors),
            namespace=namespace,
        )

        # Pinecone SDK is sync, we run it directly
        # In production, consider using asyncio.to_thread
        response = self._index.upsert(
            vectors=vectors,
            namespace=namespace or "",
        )

        upserted_count = response.upserted_count
        logger.info("Vectors upserted", count=upserted_count)

        return upserted_count

    async def search(
        self,
        vector: list[float],
        config: SearchConfig | None = None,
    ) -> list[SearchResult]:
        """Search for similar vectors in Pinecone.

        Args:
            vector: The query vector.
            config: Optional search configuration.

        Returns:
            List of search results sorted by similarity.
        """
        config = config or SearchConfig()

        logger.info(
            "Searching vectors",
            top_k=config.top_k,
            namespace=config.namespace,
            has_filter=config.filter is not None,
        )

        response = self._index.query(
            vector=vector,
            top_k=config.top_k,
            namespace=config.namespace or "",
            filter=config.filter,
            include_metadata=config.include_metadata,
            include_values=config.include_vectors,
        )

        results = [
            SearchResult(
                id=match.id,
                score=match.score,
                metadata=match.metadata or {},
                vector=match.values if config.include_vectors else None,
            )
            for match in response.matches
        ]

        logger.info("Search completed", result_count=len(results))

        return results

    async def delete(
        self,
        ids: list[str],
        namespace: str | None = None,
    ) -> int:
        """Delete vectors by ID from Pinecone.

        Args:
            ids: List of vector IDs to delete.
            namespace: Optional namespace.

        Returns:
            Number of vectors deleted.
        """
        logger.info(
            "Deleting vectors by ID",
            count=len(ids),
            namespace=namespace,
        )

        self._index.delete(
            ids=ids,
            namespace=namespace or "",
        )

        # Pinecone doesn't return count for delete
        return len(ids)

    async def delete_by_filter(
        self,
        filter: dict[str, Any],
        namespace: str | None = None,
    ) -> int:
        """Delete vectors matching a metadata filter.

        Args:
            filter: Metadata filter to match.
            namespace: Optional namespace.

        Returns:
            Number of vectors deleted (estimated).
        """
        logger.info(
            "Deleting vectors by filter",
            filter=filter,
            namespace=namespace,
        )

        self._index.delete(
            filter=filter,
            namespace=namespace or "",
        )

        # Pinecone doesn't return count for filter delete
        return 0  # Unknown

    async def fetch(
        self,
        ids: list[str],
        namespace: str | None = None,
    ) -> list[VectorRecord]:
        """Fetch vectors by ID from Pinecone.

        Args:
            ids: List of vector IDs to fetch.
            namespace: Optional namespace.

        Returns:
            List of vector records.
        """
        logger.info(
            "Fetching vectors",
            count=len(ids),
            namespace=namespace,
        )

        response = self._index.fetch(
            ids=ids,
            namespace=namespace or "",
        )

        records = [
            VectorRecord(
                id=id,
                vector=data.values,
                metadata=data.metadata or {},
            )
            for id, data in response.vectors.items()
        ]

        return records

    async def get_stats(self) -> dict[str, Any]:
        """Get statistics about the Pinecone index.

        Returns:
            Dictionary with index stats.
        """
        stats = self._index.describe_index_stats()

        return {
            "total_vector_count": stats.total_vector_count,
            "dimension": stats.dimension,
            "namespaces": {
                name: ns.vector_count
                for name, ns in stats.namespaces.items()
            },
        }

    @property
    def dimensions(self) -> int:
        """Return the dimensionality of vectors."""
        return self._dimensions

    @property
    def provider(self) -> str:
        """Return the provider name."""
        return "pinecone"
