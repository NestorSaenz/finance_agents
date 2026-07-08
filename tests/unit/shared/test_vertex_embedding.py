"""Unit tests for the Vertex embedding client (SDK client injected)."""

from types import SimpleNamespace
from typing import Any

from app.shared.clients.vertex_embedding import VertexEmbeddingClient
from app.shared.interfaces.embedding import EmbeddingConfig, EmbeddingInputType


class _FakeModels:
    def __init__(self, dim: int) -> None:
        self._dim = dim
        self.calls: list[dict[str, Any]] = []

    async def embed_content(self, *, model: str, contents: list[str], config: dict) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        return SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1] * self._dim) for _ in contents]
        )


class FakeGenaiClient:
    """Mimics google-genai's client.aio.models.embed_content."""

    def __init__(self, dim: int = 768) -> None:
        self.aio = SimpleNamespace(models=_FakeModels(dim))


def _client(dim: int = 768) -> tuple[VertexEmbeddingClient, FakeGenaiClient]:
    fake = FakeGenaiClient(dim)
    client = VertexEmbeddingClient(
        project="p", location="us-central1", model="gemini-embedding-001",
        dimensions=dim, client=fake,
    )
    return client, fake


class TestVertexEmbeddingClient:
    async def test_embed_documents_uses_dimension_and_document_task(self) -> None:
        client, fake = _client(dim=768)

        vectors = await client.embed_documents(["hola", "mundo"])

        assert len(vectors) == 2
        assert len(vectors[0]) == 768
        call = fake.aio.models.calls[-1]
        assert call["model"] == "gemini-embedding-001"
        assert call["config"]["output_dimensionality"] == 768
        assert call["config"]["task_type"] == "RETRIEVAL_DOCUMENT"

    async def test_embed_query_uses_query_task(self) -> None:
        client, fake = _client()

        vector = await client.embed_query("¿cuánto gasté?")

        assert len(vector) == 768
        assert fake.aio.models.calls[-1]["config"]["task_type"] == "RETRIEVAL_QUERY"

    async def test_embed_returns_result_with_metadata(self) -> None:
        client, _ = _client(dim=768)

        result = await client.embed(["x"], EmbeddingConfig(input_type=EmbeddingInputType.CLASSIFICATION))

        assert result.dimensions == 768
        assert result.model == "gemini-embedding-001"
        assert len(result.embeddings) == 1

    def test_properties(self) -> None:
        client, _ = _client()
        assert client.dimensions == 768
        assert client.provider == "vertex"
        assert client.model_name == "gemini-embedding-001"
