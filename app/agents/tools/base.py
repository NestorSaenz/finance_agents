"""Shared toolkit contract for the tool-calling agent.

A ``Toolkit`` exposes OpenAI-format tool schemas and dispatches a tool call to
the application service that backs it. The agent depends only on this Protocol,
so transaction/budget/goal toolkits (and the composite that aggregates them) are
interchangeable.
"""

from typing import Any, Protocol, runtime_checkable

from app.shared.types import UserId


@runtime_checkable
class Toolkit(Protocol):
    """A set of LLM-callable tools backed by application services."""

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """Tool schemas (OpenAI function format) to pass to the LLM."""
        ...

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        """Execute a tool call, binding ``user_id`` from the auth context."""
        ...
