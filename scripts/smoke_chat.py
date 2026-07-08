"""End-to-end smoke test of the chat pipeline against real providers.

Sends a natural-language message through the compiled multiagent graph and
prints the assistant's reply. Exercises: Groq (orchestrator + tool agent),
Cohere/Pinecone (categorization, best-effort), and Supabase (persistence).

Run from project root:
    uv run python scripts/smoke_chat.py "gasté 50 en pizza"
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # allow emojis in the console

from langchain_core.messages import AIMessage

from app.agents.graph import get_compiled_graph
from app.agents.state import build_initial_state
from app.core.config import settings
from app.shared.dependencies import close_database, init_database


async def main(message: str) -> None:
    print("=" * 50)
    print("Chat pipeline smoke test")
    print("=" * 50)
    print(f"User: {message}")

    await init_database()

    try:
        graph = get_compiled_graph()
        state = build_initial_state(message=message, user_id=settings.DEMO_USER_ID)
        final = await graph.ainvoke(state, config={"configurable": {"thread_id": "smoke-1"}})

        reply = next(
            (m.content for m in reversed(final.get("messages", [])) if isinstance(m, AIMessage)),
            "(no reply)",
        )
        print(f"\n[OK] intent={final.get('detected_intent')} complexity={final.get('query_complexity')}")
        print(f"Assistant: {reply}")
    except Exception as e:  # noqa: BLE001
        import traceback

        print(f"\n[ERROR] {type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        await close_database()


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "gasté 50 en pizza"
    asyncio.run(main(msg))
