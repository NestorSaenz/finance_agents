"""Centralized Dependency Injection for all external services.

This module provides a single place to configure and swap implementations.
All services depend on interfaces, not concrete implementations.

Current Stack:
- LLM: Groq (Llama 3.3 70B / Llama 3.1 8B) - Free tier
       Gemini (1.5 Pro / 1.5 Flash) - Pro quality (optional)
- Embeddings: Cohere Embed v3 Multilingual
- Vector Store: Pinecone Serverless
- Database: Supabase (PostgreSQL)

To swap a provider:
1. Create a new client implementing the interface
2. Change the factory function here
3. No changes needed in business logic!

To switch from Groq to Gemini:
1. Set GEMINI_API_KEY in .env
2. Change LLM_PROVIDER to "gemini" below
"""

from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends

from app.core.config import settings
from app.shared.clients.cohere_embedding import CohereEmbeddingClient
from app.shared.clients.gemini_llm import GeminiLLMClient
from app.shared.clients.groq_llm import GroqLLMClient
from app.shared.clients.pinecone_store import PineconeVectorStore
from app.shared.clients.supabase_client import SupabaseClient
from app.shared.interfaces.database import DatabaseInterface
from app.shared.interfaces.embedding import EmbeddingInterface
from app.shared.interfaces.llm import LLMInterface
from app.shared.interfaces.vector_store import VectorStoreInterface


# =============================================================================
# LLM Provider Configuration
# =============================================================================
# Change this to switch between providers:
# - "groq": Free tier, fast inference (Llama models)
# - "gemini": Pro quality, Google Cloud credits (Gemini models)
# =============================================================================
LLM_PROVIDER: Literal["groq", "gemini"] = "groq"


# =============================================================================
# LLM Provider - Groq (Free Tier) / Gemini (Pro Quality)
# =============================================================================
# Groq: llama-3.1-8b-instant (14.4K req/day), llama-3.3-70b-versatile (1K req/day)
# Gemini: gemini-1.5-flash (fast), gemini-1.5-pro (best quality)
# =============================================================================


@lru_cache
def get_llm_simple() -> LLMInterface:
    """Get LLM for Simple Path (fast, high limits).

    Provider depends on LLM_PROVIDER setting:
    - Groq: llama-3.1-8b-instant (14.4K requests/day)
    - Gemini: gemini-1.5-flash (fast, cheap)

    Ideal for: categorization, simple queries, quick responses.

    Returns:
        LLMInterface implementation for simple tasks.
    """
    if LLM_PROVIDER == "gemini":
        return GeminiLLMClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL_SIMPLE,
        )
    # Default: Groq
    return GroqLLMClient(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL_SIMPLE,
    )


@lru_cache
def get_llm_complex() -> LLMInterface:
    """Get LLM for Complex Path (powerful, best quality).

    Provider depends on LLM_PROVIDER setting:
    - Groq: llama-3.3-70b-versatile (1K requests/day)
    - Gemini: gemini-1.5-pro (best quality)

    Ideal for: analysis, planning, multi-step reasoning.

    Returns:
        LLMInterface implementation for complex tasks.
    """
    if LLM_PROVIDER == "gemini":
        return GeminiLLMClient(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL_COMPLEX,
        )
    # Default: Groq
    return GroqLLMClient(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL_COMPLEX,
    )


# Default LLM (uses complex model for general use)
@lru_cache
def get_llm_client() -> LLMInterface:
    """Get the default LLM client.

    Returns the complex model by default.
    Use get_llm_simple() or get_llm_complex() for specific paths.

    Returns:
        LLMInterface implementation.
    """
    return get_llm_complex()


# Type aliases for FastAPI dependency injection
LLMDep = Annotated[LLMInterface, Depends(get_llm_client)]
LLMSimpleDep = Annotated[LLMInterface, Depends(get_llm_simple)]
LLMComplexDep = Annotated[LLMInterface, Depends(get_llm_complex)]


# =============================================================================
# Embedding Provider - Cohere
# =============================================================================
# Using Cohere Embed v3 Multilingual (best for Spanish)
# Alternatives: OpenAI text-embedding-3, HuggingFace
# =============================================================================


@lru_cache
def get_embedding_client() -> EmbeddingInterface:
    """Get the embedding client instance.

    Returns:
        EmbeddingInterface implementation (Cohere Embed v3).
    """
    return CohereEmbeddingClient(
        api_key=settings.COHERE_API_KEY,
        model=settings.COHERE_EMBED_MODEL,
    )


# Type alias for FastAPI dependency injection
EmbeddingDep = Annotated[EmbeddingInterface, Depends(get_embedding_client)]


# =============================================================================
# Vector Store Provider - Pinecone
# =============================================================================
# Using Pinecone Serverless (free tier: 100K vectors)
# Alternatives: ChromaDB, Qdrant, Weaviate, pgvector
# =============================================================================


@lru_cache
def get_vector_store() -> VectorStoreInterface:
    """Get the vector store instance.

    Returns:
        VectorStoreInterface implementation (Pinecone).
    """
    return PineconeVectorStore(
        api_key=settings.PINECONE_API_KEY,
        index_name=settings.PINECONE_INDEX,
        dimensions=settings.EMBEDDING_DIMENSION,
    )


# Type alias for FastAPI dependency injection
VectorStoreDep = Annotated[VectorStoreInterface, Depends(get_vector_store)]


# =============================================================================
# Database Provider - Supabase
# =============================================================================
# Using Supabase (PostgreSQL + Auth + RLS)
# Alternatives: Direct PostgreSQL, MongoDB
# =============================================================================

# Global client instance (initialized in lifespan)
_supabase_client: SupabaseClient | None = None


async def init_database() -> None:
    """Initialize the database client.

    Called during application startup (lifespan).
    """
    global _supabase_client
    _supabase_client = await SupabaseClient.create(
        url=settings.SUPABASE_URL,
        key=settings.SUPABASE_KEY,
    )


async def close_database() -> None:
    """Close the database client.

    Called during application shutdown (lifespan).
    """
    global _supabase_client
    _supabase_client = None


def get_database() -> DatabaseInterface:
    """Get the database client instance.

    Returns:
        DatabaseInterface implementation (Supabase).

    Raises:
        RuntimeError: If database not initialized.
    """
    if _supabase_client is None:
        raise RuntimeError(
            "Database not initialized. Call init_database() in lifespan."
        )
    return _supabase_client


# Type alias for FastAPI dependency injection
DatabaseDep = Annotated[DatabaseInterface, Depends(get_database)]


# =============================================================================
# Composite Dependencies
# =============================================================================
# For services that need multiple dependencies
# =============================================================================


class AIServices:
    """Container for all AI-related services.

    Provides access to:
    - llm_simple: Fast LLM for simple tasks
    - llm_complex: Powerful LLM for complex tasks
    - embeddings: Embedding generation
    - vector_store: Vector storage and search
    """

    def __init__(
        self,
        llm_simple: LLMInterface,
        llm_complex: LLMInterface,
        embeddings: EmbeddingInterface,
        vector_store: VectorStoreInterface,
    ) -> None:
        self.llm_simple = llm_simple
        self.llm_complex = llm_complex
        self.embeddings = embeddings
        self.vector_store = vector_store

    @property
    def llm(self) -> LLMInterface:
        """Default LLM (complex model)."""
        return self.llm_complex


def get_ai_services(
    llm_simple: LLMSimpleDep,
    llm_complex: LLMComplexDep,
    embeddings: EmbeddingDep,
    vector_store: VectorStoreDep,
) -> AIServices:
    """Get all AI services as a single dependency.

    Useful for agents that need access to multiple AI services.
    """
    return AIServices(
        llm_simple=llm_simple,
        llm_complex=llm_complex,
        embeddings=embeddings,
        vector_store=vector_store,
    )


# Type alias for composite AI services
AIServicesDep = Annotated[AIServices, Depends(get_ai_services)]
