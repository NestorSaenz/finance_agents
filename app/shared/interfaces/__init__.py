"""Abstract interfaces for external services.

These interfaces define contracts that allow swapping implementations:
- LLMInterface: Cohere → OpenAI → Anthropic → Local models
- EmbeddingInterface: Cohere → OpenAI → HuggingFace
- VectorStoreInterface: Pinecone → ChromaDB → Qdrant → Weaviate
- DatabaseInterface: Supabase → PostgreSQL → MongoDB
"""

from app.shared.interfaces.database import DatabaseInterface
from app.shared.interfaces.embedding import EmbeddingInterface, EmbeddingResult
from app.shared.interfaces.llm import LLMInterface, LLMResponse, Message, MessageRole
from app.shared.interfaces.vector_store import (
    SearchResult,
    VectorMetadata,
    VectorStoreInterface,
)

__all__ = [
    # LLM
    "LLMInterface",
    "LLMResponse",
    "Message",
    "MessageRole",
    # Embedding
    "EmbeddingInterface",
    "EmbeddingResult",
    # Vector Store
    "VectorStoreInterface",
    "VectorMetadata",
    "SearchResult",
    # Database
    "DatabaseInterface",
]
