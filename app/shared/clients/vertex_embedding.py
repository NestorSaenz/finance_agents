"""Vertex AI embedding client (Google Gemini embeddings).

Implements ``EmbeddingInterface`` using the ``google-genai`` SDK against Vertex
AI, billed to the GCP project (use your Vertex credits). Authentication is via
Application Default Credentials (ADC) / a service account — there is no API key.

The ``google.genai`` import is lazy so tests can inject a fake client without
the SDK installed.
"""

from typing import Any

from app.core.logging import get_logger
from app.shared.interfaces.embedding import (
    EmbeddingConfig,
    EmbeddingInputType,
    EmbeddingInterface,
    EmbeddingResult,
)

logger = get_logger(__name__)

# Maps our generic input type to Gemini embedding task types.
_TASK_TYPES = {
    EmbeddingInputType.SEARCH_DOCUMENT: "RETRIEVAL_DOCUMENT",
    EmbeddingInputType.SEARCH_QUERY: "RETRIEVAL_QUERY",
    EmbeddingInputType.CLASSIFICATION: "CLASSIFICATION",
    EmbeddingInputType.CLUSTERING: "CLUSTERING",
}


class VertexEmbeddingClient(EmbeddingInterface):
    """Generates embeddings via Vertex AI Gemini embedding models."""

    def __init__(
        self,
        project: str,
        location: str,
        model: str,
        dimensions: int,
        client: Any | None = None,
    ) -> None:
        self._project = project
        self._location = location
        self._model = model
        self._dimensions = dimensions
        self._client = client or self._build_client(project, location)

    @staticmethod
    def _build_client(project: str, location: str) -> Any:
        from google import genai  # lazy import: only needed for real usage

        return genai.Client(vertexai=True, project=project, location=location)

    async def _embed(self, texts: list[str], input_type: EmbeddingInputType) -> list[list[float]]:
        response = await self._client.aio.models.embed_content(
            model=self._model,
            contents=texts,
            config={
                "output_dimensionality": self._dimensions,
                "task_type": _TASK_TYPES[input_type],
            },
        )
        return [embedding.values for embedding in response.embeddings]

    async def embed(
        self, texts: list[str], config: EmbeddingConfig | None = None
    ) -> EmbeddingResult:
        input_type = config.input_type if config else EmbeddingInputType.SEARCH_DOCUMENT
        vectors = await self._embed(texts, input_type)
        return EmbeddingResult(
            embeddings=vectors,
            model=self._model,
            dimensions=self._dimensions,
        )

    async def embed_query(self, query: str) -> list[float]:
        vectors = await self._embed([query], EmbeddingInputType.SEARCH_QUERY)
        return vectors[0]

    async def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return await self._embed(documents, EmbeddingInputType.SEARCH_DOCUMENT)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "vertex"
