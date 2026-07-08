"""Minimal Vertex AI connectivity check (uses ADC).

Verifies that the project + Vertex API + billing + ADC auth all work by doing a
single tiny generate call.

Run from project root:
    uv run python scripts/check_vertex.py PROJECT_ID [MODEL] [LOCATION]
"""

import asyncio
import sys

from app.shared.clients.vertex_llm import VertexLLMClient
from app.shared.interfaces.llm import LLMConfig, Message, MessageRole


async def main(project: str, model: str, location: str) -> None:
    print(f"Project:  {project}")
    print(f"Location: {location}")
    print(f"Calling {model} ...")
    try:
        client = VertexLLMClient(project=project, location=location, model=model)
        response = await client.generate(
            [Message(role=MessageRole.USER, content="Di 'hola' y nada más.")],
            LLMConfig(max_tokens=256, temperature=0),
        )
        print(f"\n[OK] Vertex works! Response: {response.content!r}")
    except Exception as e:  # noqa: BLE001
        print(f"\n[ERROR] {type(e).__name__}: {e}")


if __name__ == "__main__":
    proj = sys.argv[1] if len(sys.argv) > 1 else ""
    model_name = sys.argv[2] if len(sys.argv) > 2 else "gemini-2.0-flash"
    loc = sys.argv[3] if len(sys.argv) > 3 else "us-central1"
    asyncio.run(main(proj, model_name, loc))
