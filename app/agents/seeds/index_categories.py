"""Script to index category examples in Pinecone.

This script generates embeddings for all category examples
and stores them in Pinecone for semantic similarity search.

Run from project root:
    uv run python -m app.agents.seeds.index_categories
"""

import asyncio
import sys
import uuid

# Fix Windows encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.agents.seeds.category_examples import get_all_examples, get_category_count, get_example_count
from app.core.config import settings
from app.core.logging import get_logger
from app.shared.clients.cohere_embedding import CohereEmbeddingClient
from app.shared.clients.pinecone_store import PineconeVectorStore
from app.shared.interfaces.vector_store import VectorRecord

logger = get_logger(__name__)

NAMESPACE = "categories"
BATCH_SIZE = 50


async def index_categories() -> None:
    """Index all category examples in Pinecone."""
    # Validate configuration
    if not settings.COHERE_API_KEY:
        print("[ERROR] COHERE_API_KEY not configured in .env")
        return

    if not settings.PINECONE_API_KEY:
        print("[ERROR] PINECONE_API_KEY not configured in .env")
        return

    print("=" * 60)
    print("Indexing Category Examples in Pinecone")
    print("=" * 60)
    print(f"Categories: {get_category_count()}")
    print(f"Total examples: {get_example_count()}")
    print(f"Namespace: {NAMESPACE}")
    print("=" * 60)

    # Initialize clients
    embedding_client = CohereEmbeddingClient(
        api_key=settings.COHERE_API_KEY,
        model=settings.COHERE_EMBED_MODEL,
    )

    vector_store = PineconeVectorStore(
        api_key=settings.PINECONE_API_KEY,
        index_name=settings.PINECONE_INDEX,
        dimensions=settings.EMBEDDING_DIMENSION,
    )

    # Get all examples
    examples = get_all_examples()
    print(f"\nProcessing {len(examples)} examples...")

    # Process in batches
    total_indexed = 0

    for i in range(0, len(examples), BATCH_SIZE):
        batch = examples[i : i + BATCH_SIZE]
        descriptions = [desc for _, desc in batch]
        categories = [cat for cat, _ in batch]

        print(f"\nBatch {i // BATCH_SIZE + 1}: {len(batch)} examples")

        # Generate embeddings
        embeddings = await embedding_client.embed_documents(descriptions)

        # Create vector records
        records = []
        for j, (embedding, category, description) in enumerate(
            zip(embeddings, categories, descriptions)
        ):
            record = VectorRecord(
                id=f"cat_{category}_{uuid.uuid4().hex[:8]}",
                vector=embedding,
                metadata={
                    "category": category,
                    "description": description,
                    "type": "category_example",
                },
            )
            records.append(record)

        # Upsert to Pinecone
        upserted = await vector_store.upsert(records, namespace=NAMESPACE)
        total_indexed += upserted
        print(f"  Indexed: {upserted} vectors")

    print("\n" + "=" * 60)
    print(f"[OK] Total indexed: {total_indexed} vectors")
    print("=" * 60)

    # Show stats
    stats = await vector_store.get_stats()
    print(f"\nPinecone Index Stats:")
    print(f"  Total vectors: {stats['total_vector_count']}")
    print(f"  Namespaces: {stats['namespaces']}")


async def clear_categories() -> None:
    """Clear all category examples from Pinecone."""
    if not settings.PINECONE_API_KEY:
        print("[ERROR] PINECONE_API_KEY not configured")
        return

    print("Clearing category examples from Pinecone...")

    vector_store = PineconeVectorStore(
        api_key=settings.PINECONE_API_KEY,
        index_name=settings.PINECONE_INDEX,
        dimensions=settings.EMBEDDING_DIMENSION,
    )

    # Delete by filter
    await vector_store.delete_by_filter(
        filter={"type": "category_example"},
        namespace=NAMESPACE,
    )

    print("[OK] Category examples cleared")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Index category examples in Pinecone")
    parser.add_argument("--clear", action="store_true", help="Clear existing examples first")
    args = parser.parse_args()

    if args.clear:
        asyncio.run(clear_categories())

    asyncio.run(index_categories())
