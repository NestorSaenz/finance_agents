"""Minimal Vertex embedding connectivity check (uses ADC).

Verifies the embedding model is available in the project/region and returns the
expected dimension.

Run from project root:
    uv run python scripts/check_vertex_embedding.py [MODEL] [DIMENSIONS]
"""

import asyncio
import sys

from app.core.config import settings
from app.shared.clients.vertex_embedding import VertexEmbeddingClient


async def main(model: str, dimensions: int) -> None:
    print(f"Project:   {settings.GCP_PROJECT}")
    print(f"Location:  {settings.GCP_LOCATION}")
    print(f"Model:     {model}")
    print(f"Dimensions: {dimensions}")
    try:
        client = VertexEmbeddingClient(
            project=settings.GCP_PROJECT,
            location=settings.GCP_LOCATION,
            model=model,
            dimensions=dimensions,
        )
        vector = await client.embed_query("cena en un restaurante italiano")
        print(f"\n[OK] Embedding works! Returned dim={len(vector)}, first 3={vector[:3]}")
    except Exception as e:  # noqa: BLE001
        print(f"\n[ERROR] {type(e).__name__}: {e}")


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else settings.VERTEX_EMBED_MODEL
    d = int(sys.argv[2]) if len(sys.argv) > 2 else 768
    asyncio.run(main(m, d))
