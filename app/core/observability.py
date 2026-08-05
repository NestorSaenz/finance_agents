"""Langfuse observability for the multiagent system (LLM/agent tracing).

Wraps Langfuse behind three tiny helpers so the rest of the app never imports
the SDK directly. When Langfuse is not configured (no keys) every helper is a
safe no-op, so tests and local runs never need the SDK to be reachable.

Tracing is wired at the graph boundary: the chat route attaches the callbacks
returned by :func:`get_trace_callbacks` to ``graph.ainvoke``, so every node run
becomes a span under one trace per conversation turn (grouped by user/session).
"""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Set once at startup; guards every helper so nothing runs when Langfuse is off.
_enabled = False


def init_observability() -> None:
    """Initialize the Langfuse client if keys are configured (best-effort).

    Never raises: a tracing failure must not stop the app from starting.
    """
    global _enabled
    if not settings.has_langfuse():
        logger.info("Langfuse observability not configured")
        return
    try:
        from langfuse import Langfuse

        Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
            release=settings.RELEASE or None,
        )
        _enabled = True
        logger.info("Langfuse observability enabled", host=settings.LANGFUSE_HOST)
    except Exception as e:  # noqa: BLE001 - observability must never break startup.
        logger.error("Failed to initialize Langfuse; tracing disabled", error=str(e))


def get_trace_callbacks() -> list[Any]:
    """Return LangChain callbacks that trace the graph (empty list if disabled)."""
    if not _enabled:
        return []
    try:
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]
    except Exception as e:  # noqa: BLE001 - degrade to no tracing, never break the turn.
        logger.error("Failed to build Langfuse handler", error=str(e))
        return []


def get_langfuse_client() -> Any | None:
    """Return the Langfuse client for manual spans, or None when disabled."""
    if not _enabled:
        return None
    try:
        from langfuse import get_client

        return get_client()
    except Exception as e:  # noqa: BLE001 - degrade to no tracing.
        logger.error("Failed to get Langfuse client", error=str(e))
        return None


@contextmanager
def start_tool_span(name: str, tool_input: Any) -> Iterator[Any]:
    """Context manager for a tool-execution span; nests under the active trace.

    Yields the span (to attach output via :func:`record_tool_span`) or ``None``
    when Langfuse is disabled. A tracing failure must never break a tool call, so
    span start AND end are each guarded: if the SDK raises we degrade to a no-op.
    A real exception from the tool body still propagates (and is recorded on the
    span), so the caller and the node boundary handle it as before.
    """
    client = get_langfuse_client()
    if client is None:
        yield None
        return
    try:
        span_cm = client.start_as_current_span(name=name, input=tool_input)
        span = span_cm.__enter__()
    except Exception as e:  # noqa: BLE001 - tracing must never break a tool call.
        logger.error("Failed to start tool span", tool=name, error=str(e))
        yield None
        return
    try:
        yield span
    finally:
        # sys.exc_info() carries the tool's exception (if any) into __exit__ so it
        # is recorded on the span; a failure closing the span is swallowed, never
        # masking the tool's own result or error.
        try:
            span_cm.__exit__(*sys.exc_info())
        except Exception as e:  # noqa: BLE001 - closing the span must not break the tool.
            logger.error("Failed to end tool span", tool=name, error=str(e))


def record_tool_span(span: Any, *, output: Any, error: str | None = None) -> None:
    """Attach a tool's result (or error) to its span; no-op when span is None."""
    if span is None:
        return
    try:
        if error is not None:
            span.update(output=output, level="ERROR", status_message=error)
        else:
            span.update(output=output)
    except Exception as e:  # noqa: BLE001 - tracing must never break a tool call.
        logger.error("Failed to record tool span", error=str(e))


def flush_observability() -> None:
    """Flush pending traces (call on shutdown so nothing is lost)."""
    if not _enabled:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as e:  # noqa: BLE001 - shutdown must not raise.
        logger.error("Failed to flush Langfuse", error=str(e))
