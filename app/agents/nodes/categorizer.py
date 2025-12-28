"""Categorizer agent node.

The categorizer uses a HYBRID approach to classify transactions:
1. First, try semantic similarity with embeddings (fast, cheap)
2. If confidence < threshold, fallback to LLM (accurate, more expensive)

This provides the best balance of cost, speed, and accuracy.
"""

from app.agents.models import CategorySuggestion
from app.agents.nodes.categorizer_constants import (
    CATEGORIZATION_PROMPT,
    CATEGORY_MAPPINGS,
    DEFAULT_CATEGORIES,
    DESCRIPTION_PATTERNS,
    EMBEDDING_CONFIDENCE_THRESHOLD,
    LLM_FALLBACK_THRESHOLD,
)
from app.agents.state import AgentState
from app.agents.types import AgentName
from app.core.logging import get_logger
from app.shared.interfaces.embedding import EmbeddingInterface
from app.shared.interfaces.llm import LLMConfig, LLMInterface, Message, MessageRole
from app.shared.interfaces.vector_store import SearchConfig, VectorStoreInterface

logger = get_logger(__name__)


async def categorizer_node(
    state: AgentState,
    embedding_client: EmbeddingInterface,
    vector_store: VectorStoreInterface,
    llm: LLMInterface,
) -> AgentState:
    """Categorize a transaction using hybrid approach.

    Strategy:
    1. Generate embedding for the transaction description
    2. Search for similar transactions in vector store
    3. If confidence >= 85%, use embedding result
    4. If confidence < 85%, fallback to LLM

    Args:
        state: Current agent state with transaction description.
        embedding_client: Client for generating embeddings.
        vector_store: Vector store for similarity search.
        llm: LLM client for fallback categorization.

    Returns:
        Updated state with category suggestion.
    """
    messages = state.get("messages", [])
    user_id = state.get("user_id", "")

    if not messages:
        logger.warning("Categorizer received empty messages")
        return {
            **state,
            "category_suggestion": "otros",
            "should_respond": True,
            "next_agent": AgentName.RESPONSE_GENERATOR.value,
        }

    # Extract transaction description from the last message
    user_message = messages[-1].content
    description = _extract_description(user_message)

    logger.info(
        "Categorizer processing",
        description=description[:50],
        user_id=user_id,
    )

    # Try hybrid categorization
    suggestion = await _categorize_hybrid(
        description=description,
        embedding_client=embedding_client,
        vector_store=vector_store,
        llm=llm,
    )

    logger.info(
        "Transaction categorized",
        category=suggestion.category,
        confidence=suggestion.confidence,
        method="embedding" if suggestion.confidence >= EMBEDDING_CONFIDENCE_THRESHOLD else "llm",
    )

    return {
        **state,
        "category_suggestion": suggestion.category,
        "should_respond": True,
        "next_agent": AgentName.RESPONSE_GENERATOR.value,
    }


async def _categorize_hybrid(
    description: str,
    embedding_client: EmbeddingInterface,
    vector_store: VectorStoreInterface,
    llm: LLMInterface,
) -> CategorySuggestion:
    """Categorize using hybrid approach: embeddings first, LLM fallback."""
    try:
        # Step 1: Try embedding-based categorization
        embedding_result = await _categorize_with_embeddings(
            description=description,
            embedding_client=embedding_client,
            vector_store=vector_store,
        )

        # Step 2: Check confidence
        if embedding_result.confidence >= EMBEDDING_CONFIDENCE_THRESHOLD:
            logger.debug("Using embedding result", confidence=embedding_result.confidence)
            return embedding_result

        # Step 3: Fallback to LLM
        logger.debug(
            "Embedding confidence too low, falling back to LLM",
            embedding_confidence=embedding_result.confidence,
        )
        llm_result = await _categorize_with_llm(description, llm)

        # If embedding had some confidence, include it as alternative
        if embedding_result.confidence >= LLM_FALLBACK_THRESHOLD:
            llm_result.alternatives = [embedding_result.category]

        return llm_result

    except Exception as e:
        logger.error("Hybrid categorization failed", error=str(e))
        return CategorySuggestion(category="otros", confidence=0.0, alternatives=[])


async def _categorize_with_embeddings(
    description: str,
    embedding_client: EmbeddingInterface,
    vector_store: VectorStoreInterface,
) -> CategorySuggestion:
    """Categorize using embedding similarity search."""
    query_embedding = await embedding_client.embed_query(description)

    search_config = SearchConfig(
        top_k=5,
        namespace="categories",
        include_metadata=True,
    )
    results = await vector_store.search(query_embedding, search_config)

    if not results:
        return CategorySuggestion(category="otros", confidence=0.0, alternatives=[])

    top_result = results[0]
    category = top_result.metadata.get("category", "otros")
    confidence = top_result.score

    alternatives = [
        r.metadata.get("category", "otros")
        for r in results[1:3]
        if r.metadata.get("category") != category
    ]

    return CategorySuggestion(
        category=category,
        confidence=confidence,
        alternatives=alternatives,
    )


async def _categorize_with_llm(description: str, llm: LLMInterface) -> CategorySuggestion:
    """Categorize using LLM."""
    categories_str = ", ".join(DEFAULT_CATEGORIES)
    prompt = CATEGORIZATION_PROMPT.format(
        categories=categories_str,
        description=description,
    )

    config = LLMConfig(temperature=0.1, max_tokens=20)
    response = await llm.generate(
        messages=[Message(role=MessageRole.USER, content=prompt)],
        config=config,
    )

    category = response.content.strip().lower()
    if category not in DEFAULT_CATEGORIES:
        category = _find_closest_category(category)

    return CategorySuggestion(category=category, confidence=0.95, alternatives=[])


def _find_closest_category(category: str) -> str:
    """Find closest matching category."""
    category = category.lower().strip()

    if category in DEFAULT_CATEGORIES:
        return category

    if category in CATEGORY_MAPPINGS:
        return CATEGORY_MAPPINGS[category]

    # Check if any mapping key is in the category
    for key, value in CATEGORY_MAPPINGS.items():
        if key in category:
            return value

    return "otros"


def _extract_description(message: str) -> str:
    """Extract transaction description from user message."""
    message_lower = message.lower()

    for pattern in DESCRIPTION_PATTERNS:
        if pattern in message_lower:
            idx = message_lower.find(pattern)
            return message[idx + len(pattern) :].strip()

    return message.strip()
