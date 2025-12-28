"""Dependency injection for the agent system.

This module provides FastAPI dependencies for injecting
agent-related services and clients.
"""

from typing import Annotated

from fastapi import Depends

from app.agents.nodes.classifier import classify_query
from app.core.config import settings
from app.shared.clients.groq_llm import GroqLLMClient
from app.shared.interfaces.llm import LLMInterface


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


# Type aliases for FastAPI dependency injection
ClassifierLLMDep = Annotated[LLMInterface, Depends(get_classifier_llm)]
AgentLLMDep = Annotated[LLMInterface, Depends(get_agent_llm)]


__all__ = [
    "get_classifier_llm",
    "get_agent_llm",
    "ClassifierLLMDep",
    "AgentLLMDep",
    "classify_query",
]
