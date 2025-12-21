"""Categorizer agent node.

The categorizer uses semantic similarity to classify transactions
into appropriate categories using embeddings and vector search.

This agent demonstrates the modular architecture:
- Uses EmbeddingInterface (can be Cohere, OpenAI, etc.)
- Uses VectorStoreInterface (can be Pinecone, Chroma, etc.)
"""

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.shared.dependencies import get_embedding_client, get_vector_store
from app.shared.interfaces.vector_store import SearchConfig

logger = get_logger(__name__)

# Category mapping from vector search results
CATEGORY_THRESHOLD = 0.7  # Minimum similarity score to accept a category


async def categorizer_node(state: AgentState) -> AgentState:
    """Categorize a transaction using semantic similarity.

    Uses embedding + vector search to find similar transactions
    and determine the most likely category.

    Args:
        state: Current agent state with transaction description.

    Returns:
        Updated state with category suggestion.
    """
    messages = state.get("messages", [])
    user_id = state.get("user_id", "")

    if not messages:
        logger.warning("Categorizer received empty messages")
        return {
            **state,
            "category_suggestion": "other",
            "should_respond": True,
        }

    # Extract transaction description from the last message
    user_message = messages[-1].content
    description = _extract_description(user_message)

    logger.info(
        "Categorizer processing",
        description_length=len(description),
        user_id=user_id,
    )

    try:
        # Get interfaces (these can be swapped without changing this code!)
        embeddings = get_embedding_client()
        vector_store = get_vector_store()

        # 1. Generate embedding for the description
        query_embedding = await embeddings.embed_query(description)

        # 2. Search for similar transactions
        search_config = SearchConfig(
            top_k=5,
            filter={"user_id": user_id} if user_id else None,
            include_metadata=True,
        )
        results = await vector_store.search(query_embedding, search_config)

        # 3. Determine category from similar transactions
        category = _determine_category_from_results(results)

        logger.info(
            "Transaction categorized",
            category=category,
            similar_count=len(results),
            top_score=results[0].score if results else 0,
        )

    except Exception as e:
        logger.error("Categorization failed", error=str(e))
        category = "other"

    return {
        **state,
        "category_suggestion": category,
        "should_respond": True,
    }


def _extract_description(message: str) -> str:
    """Extract transaction description from user message.

    Args:
        message: User's message.

    Returns:
        Extracted description.
    """
    # Simple extraction - in production, use LLM for better extraction
    # Look for common patterns like "gasté en X" or "compré X"
    keywords = ["gasté en", "compré", "pagué", "registra", "agrega"]

    for keyword in keywords:
        if keyword in message.lower():
            # Extract text after the keyword
            idx = message.lower().find(keyword)
            return message[idx + len(keyword) :].strip()

    return message


def _determine_category_from_results(
    results: list,
) -> str:
    """Determine category based on similar transactions.

    Uses weighted voting based on similarity scores.

    Args:
        results: Search results from vector store.

    Returns:
        Most likely category.
    """
    if not results:
        return "other"

    # Check if top result is confident enough
    if results[0].score >= CATEGORY_THRESHOLD:
        return results[0].metadata.get("category", "other")

    # Weighted voting by similarity score
    category_scores: dict[str, float] = {}

    for result in results:
        category = result.metadata.get("category", "other")
        score = result.score

        if category in category_scores:
            category_scores[category] += score
        else:
            category_scores[category] = score

    # Return category with highest weighted score
    if category_scores:
        return max(category_scores, key=category_scores.get)

    return "other"
