"""Unit tests for the semantic transaction categorizer."""

from app.shared.types import CategoryType
from app.src.transactions.services.semantic_categorizer import (
    SemanticTransactionCategorizer,
)
from tests.fakes import FakeEmbeddingClient, FakeVectorStore


class TestSemanticCategorizer:
    async def test_returns_match_above_threshold(self) -> None:
        categorizer = SemanticTransactionCategorizer(
            FakeEmbeddingClient(),
            FakeVectorStore(category="restaurantes", score=0.95),
        )
        assert await categorizer.categorize("cena en restaurante") == CategoryType.RESTAURANTES

    async def test_low_confidence_returns_otros(self) -> None:
        categorizer = SemanticTransactionCategorizer(
            FakeEmbeddingClient(),
            FakeVectorStore(category="restaurantes", score=0.10),
        )
        assert await categorizer.categorize("algo ambiguo") == CategoryType.OTROS

    async def test_unknown_category_returns_otros(self) -> None:
        categorizer = SemanticTransactionCategorizer(
            FakeEmbeddingClient(),
            FakeVectorStore(category="not-a-real-category", score=0.99),
        )
        assert await categorizer.categorize("x") == CategoryType.OTROS

    async def test_embedding_failure_degrades_to_otros(self) -> None:
        class BrokenEmbedding(FakeEmbeddingClient):
            async def embed_query(self, text: str) -> list[float]:
                raise RuntimeError("cohere down")

        categorizer = SemanticTransactionCategorizer(BrokenEmbedding(), FakeVectorStore())
        assert await categorizer.categorize("x") == CategoryType.OTROS
