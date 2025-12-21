"""Vector Store Interface - Abstract contract for vector database providers.

Implementations:
- PineconeVectorStore: Pinecone Serverless
- ChromaVectorStore: ChromaDB (local or cloud)
- QdrantVectorStore: Qdrant
- WeaviateVectorStore: Weaviate
- PgVectorStore: PostgreSQL with pgvector
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorMetadata:
    """Metadata associated with a vector."""

    id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorRecord:
    """A vector record to upsert."""

    id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """Result of a vector search."""

    id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    vector: list[float] | None = None  # Optional, if include_vectors=True


@dataclass
class SearchConfig:
    """Configuration for vector search."""

    top_k: int = 10
    filter: dict[str, Any] | None = None  # Metadata filter
    include_metadata: bool = True
    include_vectors: bool = False
    namespace: str | None = None  # For Pinecone namespaces


class VectorStoreInterface(ABC):
    """Abstract interface for vector store providers.

    This interface allows swapping vector databases without changing
    the business logic. All vector store clients must implement this contract.

    Example usage:
        ```python
        # In dependencies.py
        def get_vector_store() -> VectorStoreInterface:
            return PineconeVectorStore(
                api_key=settings.PINECONE_API_KEY,
                index_name=settings.PINECONE_INDEX,
            )

        # In service
        class TransactionSearchService:
            def __init__(
                self,
                vector_store: VectorStoreInterface,
                embeddings: EmbeddingInterface,
            ):
                self.vector_store = vector_store
                self.embeddings = embeddings

            async def find_similar(self, description: str) -> list[SearchResult]:
                embedding = await self.embeddings.embed_query(description)
                return await self.vector_store.search(embedding, top_k=5)
        ```
    """

    @abstractmethod
    async def upsert(
        self,
        records: list[VectorRecord],
        namespace: str | None = None,
    ) -> int:
        """Insert or update vectors in the store.

        Args:
            records: List of vector records to upsert.
            namespace: Optional namespace (for Pinecone).

        Returns:
            Number of vectors upserted.

        Raises:
            VectorStoreError: If the operation fails.
        """
        pass

    @abstractmethod
    async def search(
        self,
        vector: list[float],
        config: SearchConfig | None = None,
    ) -> list[SearchResult]:
        """Search for similar vectors.

        Args:
            vector: The query vector.
            config: Optional search configuration.

        Returns:
            List of search results sorted by similarity.

        Raises:
            VectorStoreError: If the search fails.
        """
        pass

    @abstractmethod
    async def delete(
        self,
        ids: list[str],
        namespace: str | None = None,
    ) -> int:
        """Delete vectors by ID.

        Args:
            ids: List of vector IDs to delete.
            namespace: Optional namespace (for Pinecone).

        Returns:
            Number of vectors deleted.

        Raises:
            VectorStoreError: If the deletion fails.
        """
        pass

    @abstractmethod
    async def delete_by_filter(
        self,
        filter: dict[str, Any],
        namespace: str | None = None,
    ) -> int:
        """Delete vectors matching a metadata filter.

        Args:
            filter: Metadata filter to match.
            namespace: Optional namespace (for Pinecone).

        Returns:
            Number of vectors deleted.

        Raises:
            VectorStoreError: If the deletion fails.
        """
        pass

    @abstractmethod
    async def fetch(
        self,
        ids: list[str],
        namespace: str | None = None,
    ) -> list[VectorRecord]:
        """Fetch vectors by ID.

        Args:
            ids: List of vector IDs to fetch.
            namespace: Optional namespace (for Pinecone).

        Returns:
            List of vector records.

        Raises:
            VectorStoreError: If the fetch fails.
        """
        pass

    @abstractmethod
    async def get_stats(self) -> dict[str, Any]:
        """Get statistics about the vector store.

        Returns:
            Dictionary with stats (e.g., total vectors, dimensions).
        """
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the dimensionality of vectors in the store."""
        pass

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return the provider name (e.g., 'pinecone', 'chroma')."""
        pass
