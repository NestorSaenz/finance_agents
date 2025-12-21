"""Cohere Embedding Client - Implementation of EmbeddingInterface for Cohere.

Uses Cohere's Embed v3 Multilingual model for embeddings.
"""

import cohere

from app.core.logging import get_logger
from app.shared.interfaces.embedding import (
    EmbeddingConfig,
    EmbeddingInputType,
    EmbeddingInterface,
    EmbeddingResult,
)

logger = get_logger(__name__)


class CohereEmbeddingClient(EmbeddingInterface):
    """Cohere implementation of EmbeddingInterface.

    Uses Cohere's Embed v3 Multilingual for generating embeddings.
    Supports different input types for optimized search/classification.
    """

    # Mapping from our input types to Cohere's
    INPUT_TYPE_MAP = {
        EmbeddingInputType.SEARCH_DOCUMENT: "search_document",
        EmbeddingInputType.SEARCH_QUERY: "search_query",
        EmbeddingInputType.CLASSIFICATION: "classification",
        EmbeddingInputType.CLUSTERING: "clustering",
    }

    def __init__(
        self,
        api_key: str,
        model: str = "embed-multilingual-v3.0",
    ) -> None:
        """Initialize the Cohere embedding client.

        Args:
            api_key: Cohere API key.
            model: Embedding model name (default: embed-multilingual-v3.0).
        """
        self._client = cohere.AsyncClient(api_key=api_key)
        self._model = model
        self._dimensions = 1024  # Embed v3 produces 1024-dim vectors
        logger.info("Cohere embedding client initialized", model=model)

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
        """
        config = config or EmbeddingConfig()
        input_type = self.INPUT_TYPE_MAP.get(
            config.input_type,
            "search_document",
        )

        logger.info(
            "Generating embeddings",
            model=self._model,
            text_count=len(texts),
            input_type=input_type,
        )

        response = await self._client.embed(
            model=self._model,
            texts=texts,
            input_type=input_type,
            truncate="END" if config.truncate else "NONE",
        )

        logger.info(
            "Embeddings generated",
            dimensions=len(response.embeddings[0]) if response.embeddings else 0,
        )

        return EmbeddingResult(
            embeddings=response.embeddings,
            model=self._model,
            dimensions=self._dimensions,
            metadata={
                "input_type": input_type,
            },
        )

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a search query.

        Args:
            query: The search query text.

        Returns:
            The embedding vector for the query.
        """
        config = EmbeddingConfig(input_type=EmbeddingInputType.SEARCH_QUERY)
        result = await self.embed([query], config)
        return result.embeddings[0]

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        """Generate embeddings for documents to be stored.

        Args:
            documents: List of document texts.

        Returns:
            List of embedding vectors.
        """
        config = EmbeddingConfig(input_type=EmbeddingInputType.SEARCH_DOCUMENT)
        result = await self.embed(documents, config)
        return result.embeddings

    @property
    def dimensions(self) -> int:
        """Return the dimensionality of the embeddings."""
        return self._dimensions

    @property
    def model_name(self) -> str:
        """Return the model name."""
        return self._model

    @property
    def provider(self) -> str:
        """Return the provider name."""
        return "cohere"
