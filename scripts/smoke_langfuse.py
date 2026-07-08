"""Send one traced chat turn through the graph to verify Langfuse tracing.

Mirrors what the /chat route does: init observability -> attach the Langfuse
callback + user/session metadata to graph.ainvoke -> flush. After running,
open https://cloud.langfuse.com -> Tracing and you should see the trace.

Run from project root:
    uv run python scripts/smoke_langfuse.py "gasté 50 en pizza"
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from langchain_core.messages import AIMessage

from app.agents.graph import get_compiled_graph
from app.agents.state import build_initial_state
from app.core.config import settings
from app.core.observability import (
    flush_observability,
    get_trace_callbacks,
    init_observability,
)
from app.shared.dependencies import close_database, init_database


async def main(message: str) -> None:
    print("=" * 60)
    print("Langfuse tracing smoke test")
    print("=" * 60)
    print(f"configured: {settings.has_langfuse()}  host: {settings.LANGFUSE_HOST}")

    init_observability()
    callbacks = get_trace_callbacks()
    print(f"callbacks attached: {len(callbacks)}")

    await init_database()
    try:
        graph = get_compiled_graph()
        state = build_initial_state(message=message, user_id=settings.DEMO_USER_ID)
        config = {"configurable": {"thread_id": "langfuse-smoke"}}
        if callbacks:
            config["callbacks"] = callbacks
            config["run_name"] = "financegpt-chat"
            config["metadata"] = {
                "langfuse_user_id": settings.DEMO_USER_ID,
                "langfuse_session_id": "langfuse-smoke-session",
            }

        final = await graph.ainvoke(state, config=config)
        reply = next(
            (m.content for m in reversed(final.get("messages", [])) if isinstance(m, AIMessage)),
            "(no reply)",
        )
        print(f"\n[OK] intent={final.get('detected_intent')}")
        print(f"Assistant: {reply}")
    finally:
        flush_observability()  # push the trace before the process exits
        await close_database()
        print("\nFlushed. Check https://cloud.langfuse.com -> Tracing (session 'langfuse-smoke-session').")


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "gasté 50 en pizza"
    asyncio.run(main(msg))
