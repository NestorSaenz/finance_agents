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
from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.shared.clients.supabase_client import SupabaseClient
from app.shared.interfaces.database import DatabaseInterface
from app.shared.interfaces.embedding import EmbeddingInterface
from app.shared.interfaces.llm import LLMInterface
from app.shared.interfaces.vector_store import VectorStoreInterface

# =============================================================================
# LLM Provider Configuration
# =============================================================================
# Selected via settings.LLM_PROVIDER:
# - "groq": Free tier, fast inference (Llama models)
# - "gemini": Google AI Studio (API key)
# - "vertex": Vertex AI Gemini (GCP credits, ADC auth)
# =============================================================================


def _build_llm(provider: str, model: str) -> LLMInterface:
    """Build a single LLM client, tracing it with Langfuse when configured."""
    client = _raw_llm(provider, model)
    if settings.has_langfuse():
        from app.shared.clients.traced_llm import TracedLLMClient

        return TracedLLMClient(client)
    return client


def _raw_llm(provider: str, model: str) -> LLMInterface:
    """Build a single untraced LLM client for an explicit provider + model.

    Imports are lazy so an unused provider's SDK need not be installed.
    """
    if provider == "vertex":
        from app.shared.clients.vertex_llm import VertexLLMClient

        return VertexLLMClient(
            project=settings.GCP_PROJECT,
            location=settings.GCP_LOCATION,
            model=model,
        )
    from app.shared.clients.groq_llm import GroqLLMClient

    return GroqLLMClient(api_key=settings.GROQ_API_KEY, model=model)


def _tier_model(provider: str, tier: str) -> str:
    """Return the model name for a provider and tier ("simple" | "complex")."""
    models = {
        "vertex": (settings.VERTEX_LLM_MODEL_SIMPLE, settings.VERTEX_LLM_MODEL_COMPLEX),
        "groq": (settings.GROQ_MODEL_SIMPLE, settings.GROQ_MODEL_COMPLEX),
    }.get(provider, (settings.GROQ_MODEL_SIMPLE, settings.GROQ_MODEL_COMPLEX))
    return models[0] if tier == "simple" else models[1]


def _llm_chain(tier: str) -> LLMInterface:
    """Build the LLM (with fallback chain) for a tier.

    Chain: primary provider/model -> same-provider rescue (Vertex's other Gemini
    model, for model overload) -> cross-provider fallback (Groq, for a full
    Vertex outage). Each link covers a different failure mode.
    """
    primary = settings.LLM_PROVIDER
    specs: list[tuple[str, str]] = [(primary, _tier_model(primary, tier))]

    if settings.LLM_FALLBACK_ENABLED:
        if primary == "vertex":
            rescue_tier = "complex" if tier == "simple" else "simple"
            specs.append(("vertex", _tier_model("vertex", rescue_tier)))
        if primary != "groq" and settings.GROQ_API_KEY:
            specs.append(("groq", _tier_model("groq", "complex")))

    clients = [_build_llm(provider, model) for provider, model in specs]
    if len(clients) == 1:
        return clients[0]

    from app.shared.clients.fallback_llm import FallbackLLMClient

    return FallbackLLMClient(clients)


@lru_cache
def get_llm_simple() -> LLMInterface:
    """Get the fast LLM (with fallback) for classification/categorization."""
    return _llm_chain("simple")


@lru_cache
def get_llm_complex() -> LLMInterface:
    """Get the capable LLM (with fallback) for analysis, planning, tools."""
    return _llm_chain("complex")


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


@lru_cache
def get_llm_vision() -> LLMInterface:
    """Vision-capable LLM for image ingestion (Vertex Gemini).

    Groq is text-only, so the cross-provider fallback is skipped here: on a Vertex
    outage a vision request simply fails rather than silently dropping the image.
    Keeps the same-provider (other Gemini model) rescue for model overload.
    """
    if settings.LLM_PROVIDER != "vertex":
        return get_llm_complex()

    specs: list[tuple[str, str]] = [("vertex", _tier_model("vertex", "complex"))]
    if settings.LLM_FALLBACK_ENABLED:
        specs.append(("vertex", _tier_model("vertex", "simple")))
    clients = [_build_llm(provider, model) for provider, model in specs]
    if len(clients) == 1:
        return clients[0]

    from app.shared.clients.fallback_llm import FallbackLLMClient

    return FallbackLLMClient(clients)


# Type aliases for FastAPI dependency injection
LLMDep = Annotated[LLMInterface, Depends(get_llm_client)]
LLMSimpleDep = Annotated[LLMInterface, Depends(get_llm_simple)]
LLMComplexDep = Annotated[LLMInterface, Depends(get_llm_complex)]
LLMVisionDep = Annotated[LLMInterface, Depends(get_llm_vision)]


# =============================================================================
# Embedding Provider - Cohere
# =============================================================================
# Using Cohere Embed v3 Multilingual (best for Spanish)
# Alternatives: OpenAI text-embedding-3, HuggingFace
# =============================================================================


@lru_cache
def get_embedding_client() -> EmbeddingInterface:
    """Get the embedding client (Vertex AI Gemini embeddings, 768 dims)."""
    from app.shared.clients.vertex_embedding import VertexEmbeddingClient

    return VertexEmbeddingClient(
        project=settings.GCP_PROJECT,
        location=settings.GCP_LOCATION,
        model=settings.VERTEX_EMBED_MODEL,
        dimensions=settings.EMBEDDING_DIMENSION,
    )


# Type alias for FastAPI dependency injection
EmbeddingDep = Annotated[EmbeddingInterface, Depends(get_embedding_client)]


# =============================================================================
# Vector Store Provider - Pinecone
# =============================================================================
# Using Pinecone Serverless (free tier: 100K vectors)
# Alternatives: ChromaDB, Qdrant, Weaviate, pgvector
# =============================================================================


def get_vector_store() -> VectorStoreInterface:
    """Get the vector store (Postgres + pgvector inside Supabase).

    Not ``lru_cache``d: it wraps the mutable DB singleton, so it must be built
    fresh against the current connection (run migration 003_pgvector.sql first).
    """
    from app.shared.clients.pgvector_store import PgVectorStore

    return PgVectorStore(get_database(), dimensions=settings.EMBEDDING_DIMENSION)


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
