"""Dependency injection for the agent system.

This module provides FastAPI dependencies for injecting
agent-related services and clients.
"""

from typing import Annotated

from fastapi import Depends

from app.agents.nodes.classifier import classify_query
from app.core.config import settings
from app.shared.clients.cohere_embedding import CohereEmbeddingClient
from app.shared.clients.groq_llm import GroqLLMClient
from app.shared.clients.pinecone_store import PineconeVectorStore
from app.shared.interfaces.embedding import EmbeddingInterface
from app.shared.interfaces.llm import LLMInterface
from app.shared.interfaces.vector_store import VectorStoreInterface


# =============================================================================
# LLM Dependencies
# =============================================================================


def get_classifier_llm() -> LLMInterface:
    """Get LLM client optimized for classification.

    Uses a fast, efficient model for quick classification.

    Returns:
        LLMInterface configured for classification tasks.
    """
    return GroqLLMClient(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL_SIMPLE,  # Fast model for classification
    )


def get_agent_llm() -> LLMInterface:
    """Get LLM client for agent operations.

    Uses a more capable model for complex agent tasks.

    Returns:
        LLMInterface configured for agent operations.
    """
    return GroqLLMClient(
        api_key=settings.GROQ_API_KEY,
        model=settings.GROQ_MODEL_COMPLEX,  # More capable model
    )


# =============================================================================
# Embedding Dependencies
# =============================================================================


def get_embedding_client() -> EmbeddingInterface:
    """Get embedding client for semantic search.

    Returns:
        EmbeddingInterface configured for Cohere embeddings.
    """
    return CohereEmbeddingClient(
        api_key=settings.COHERE_API_KEY,
        model=settings.COHERE_EMBED_MODEL,
    )


# =============================================================================
# Vector Store Dependencies
# =============================================================================


def get_vector_store() -> VectorStoreInterface:
    """Get vector store for similarity search.

    Returns:
        VectorStoreInterface configured for Pinecone.
    """
    return PineconeVectorStore(
        api_key=settings.PINECONE_API_KEY,
        index_name=settings.PINECONE_INDEX,
        dimensions=settings.EMBEDDING_DIMENSION,
    )


# =============================================================================
# Type Aliases for FastAPI Dependency Injection
# =============================================================================

ClassifierLLMDep = Annotated[LLMInterface, Depends(get_classifier_llm)]
AgentLLMDep = Annotated[LLMInterface, Depends(get_agent_llm)]
EmbeddingClientDep = Annotated[EmbeddingInterface, Depends(get_embedding_client)]
VectorStoreDep = Annotated[VectorStoreInterface, Depends(get_vector_store)]


__all__ = [
    # LLM
    "get_classifier_llm",
    "get_agent_llm",
    "ClassifierLLMDep",
    "AgentLLMDep",
    # Embedding
    "get_embedding_client",
    "EmbeddingClientDep",
    # Vector Store
    "get_vector_store",
    "VectorStoreDep",
    # Functions
    "classify_query",
]
