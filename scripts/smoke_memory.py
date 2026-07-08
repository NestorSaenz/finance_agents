"""End-to-end smoke test of the long-term Memory Agent against real providers.

Exercises the full loop: baseline context -> process() extracts durable facts
from a turn (real Vertex LLM) and upserts them (real Supabase) -> get_context()
reads them back. This is what the /chat route does fire-and-forget after a turn.

Run from project root:
    uv run python scripts/smoke_memory.py
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # allow emojis/accents in the console

from app.core.config import settings
from app.shared.dependencies import (
    close_database,
    get_database,
    get_llm_simple,
    init_database,
)
from app.src.memory.repositories.user_knowledge_repository import (
    UserKnowledgeRepository,
)
from app.src.memory.services.memory_agent_service import MemoryAgentService

USER_MESSAGE = (
    "Soy diseñador freelance y cobro en dólares. Mi meta es ahorrar para un "
    "viaje a Japón el próximo año."
)
ASSISTANT_MESSAGE = "¡Anotado! Te ayudo a planear ese ahorro para Japón."


async def main() -> None:
    print("=" * 60)
    print("Memory Agent smoke test")
    print("=" * 60)

    await init_database()
    try:
        repo = UserKnowledgeRepository(get_database())
        service = MemoryAgentService(repo, get_llm_simple())
        user_id = settings.DEMO_USER_ID

        before = await service.get_context(user_id)
        print(f"\n[baseline] contexto previo:\n{before or '  (vacío)'}")

        print(f"\n[turn] usuario: {USER_MESSAGE}")
        await service.process(user_id, USER_MESSAGE, ASSISTANT_MESSAGE)

        after = await service.get_context(user_id)
        print(f"\n[result] contexto tras extracción:\n{after or '  (vacío)'}")

        if after and after != before:
            print("\n[OK] El Memory Agent extrajo y persistió hechos nuevos.")
        else:
            print("\n[WARN] No hubo cambios (¿ya estaban guardados o no se extrajo nada?).")
    except Exception as e:  # noqa: BLE001
        import traceback

        print(f"\n[ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
