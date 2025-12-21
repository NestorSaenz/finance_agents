"""Embedding Interface - Abstract contract for embedding providers.

Implementations:
- CohereEmbeddingClient: Cohere Embed v3
- OpenAIEmbeddingClient: text-embedding-3-small/large
- HuggingFaceEmbeddingClient: Local models
- PineconeInferenceClient: Pinecone's built-in embeddings
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EmbeddingInputType(str, Enum):
    """Type of input for embedding generation.

    Some providers optimize embeddings based on the intended use case.
    """

    SEARCH_DOCUMENT = "search_document"  # For documents to be searched
    SEARCH_QUERY = "search_query"  # For search queries
    CLASSIFICATION = "classification"  # For classification tasks
    CLUSTERING = "clustering"  # For clustering tasks


@dataclass
class EmbeddingResult:
    """Result of an embedding operation."""

    embeddings: list[list[float]]
    model: str
    dimensions: int

    # Usage statistics
    total_tokens: int = 0

    # Provider-specific metadata
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""

    input_type: EmbeddingInputType = EmbeddingInputType.SEARCH_DOCUMENT
    truncate: bool = True  # Whether to truncate long inputs


class EmbeddingInterface(ABC):
    """Abstract interface for embedding providers.

    This interface allows swapping embedding providers without changing
    the business logic. All embedding clients must implement this contract.

    Example usage:
        ```python
        # In dependencies.py
        def get_embedding_client() -> EmbeddingInterface:
            return CohereEmbeddingClient(api_key=settings.COHERE_API_KEY)

        # In service
        class CategorizationService:
            def __init__(self, embeddings: EmbeddingInterface):
                self.embeddings = embeddings

            async def get_embedding(self, text: str) -> list[float]:
                result = await self.embeddings.embed([text])
                return result.embeddings[0]
        ```
    """

    @abstractmethod
    async def embed(
        self,
        texts: list[str],
        config: EmbeddingConfig | None = None,
    ) -> EmbeddingResult:
        """Generate embeddings for a list of texts.

        Args:
            texts: List of texts to embed.
            config: Optional configuration for this call.

        Returns:
            EmbeddingResult with the generated embeddings.

        Raises:
            EmbeddingError: If the embedding call fails.
        """
        pass

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a search query.

        Convenience method that uses the appropriate input type for queries.

        Args:
            query: The search query text.

        Returns:
            The embedding vector for the query.
        """
        pass

    @abstractmethod
    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        """Generate embeddings for documents to be stored.

        Convenience method that uses the appropriate input type for documents.

        Args:
            documents: List of document texts.

        Returns:
            List of embedding vectors.
        """
        pass

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Return the dimensionality of the embeddings."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the name of the embedding model."""
        pass

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return the provider name (e.g., 'cohere', 'openai')."""
        pass
