"""Semantic auto-categorization for transactions.

Reuses the same embedding model and Pinecone index (``categories`` namespace)
that the categorizer agent uses, so manual and conversational transactions are
categorized consistently.
"""

from app.core.logging import get_logger
from app.shared.interfaces.embedding import EmbeddingInterface
from app.shared.interfaces.vector_store import SearchConfig, VectorStoreInterface
from app.shared.types import Category, CategoryType

from ..constants import CATEGORIES_NAMESPACE, CATEGORY_CONFIDENCE_THRESHOLD
from ..interfaces import TransactionCategorizerABC

logger = get_logger(__name__)


class SemanticTransactionCategorizer(TransactionCategorizerABC):
    """Categorizes a description via nearest-neighbour search over category examples."""

    def __init__(
        self,
        embedding_client: EmbeddingInterface,
        vector_store: VectorStoreInterface,
        threshold: float = CATEGORY_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._threshold = threshold

    async def categorize(self, description: str) -> Category:
        """Return the best-matching known category, or OTROS when unsure.

        Auto-categorization always resolves to a canonical ``CategoryType`` value;
        custom (user-defined) categories only ever arrive via explicit input.
        """
        try:
            vector = await self._embedding_client.embed_query(description)
            results = await self._vector_store.search(
                vector,
                SearchConfig(top_k=1, namespace=CATEGORIES_NAMESPACE, include_metadata=True),
            )
        except Exception as e:  # noqa: BLE001 - external service boundary: degrade to OTROS.
            logger.error("Semantic categorization failed", error=str(e))
            return CategoryType.OTROS.value

        if not results or results[0].score < self._threshold:
            return CategoryType.OTROS.value

        raw_category = results[0].metadata.get("category", "")
        try:
            return CategoryType(raw_category).value
        except ValueError:
            logger.warning("Unknown category from vector store", raw_category=raw_category)
            return CategoryType.OTROS.value
