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
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]  # TextIO on Win

from app.agents.seeds.category_examples import get_all_examples, get_category_count, get_example_count
from app.core.logging import get_logger
from app.shared.dependencies import (
    close_database,
    get_embedding_client,
    get_vector_store,
    init_database,
)
from app.shared.interfaces.vector_store import VectorRecord

logger = get_logger(__name__)

NAMESPACE = "categories"
BATCH_SIZE = 50


async def index_categories() -> None:
    """Index all category examples in the configured vector store."""
    print("=" * 60)
    print("Indexing Category Examples")
    print("=" * 60)
    print("Embeddings: Vertex AI | Vector store: pgvector (Supabase)")
    print(f"Categories: {get_category_count()}")
    print(f"Total examples: {get_example_count()}")
    print(f"Namespace: {NAMESPACE}")
    print("=" * 60)

    # pgvector lives inside Supabase, so the DB client must be initialized first.
    await init_database()

    # Resolve clients from the configured providers (respects the .env flags).
    embedding_client = get_embedding_client()
    vector_store = get_vector_store()

    # Clear the namespace first so re-runs stay idempotent (no duplicates).
    try:
        await vector_store.delete_by_filter(
            filter={"type": "category_example"}, namespace=NAMESPACE
        )
    except Exception as e:  # noqa: BLE001 - best-effort clear before seeding.
        logger.warning("Could not clear namespace before seeding", error=str(e))

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
        for embedding, category, description in zip(
            embeddings, categories, descriptions, strict=False
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

        # Upsert to the vector store
        upserted = await vector_store.upsert(records, namespace=NAMESPACE)
        total_indexed += upserted
        print(f"  Indexed: {upserted} vectors")

    print("\n" + "=" * 60)
    print(f"[OK] Total indexed: {total_indexed} vectors")
    print("=" * 60)

    # Show stats (shape varies by provider)
    stats = await vector_store.get_stats()
    print("\nVector Store Stats:")
    print(f"  Total vectors: {stats.get('total_vector_count', '?')}")
    if "namespaces" in stats:
        print(f"  Namespaces: {stats['namespaces']}")

    await close_database()


if __name__ == "__main__":
    asyncio.run(index_categories())
