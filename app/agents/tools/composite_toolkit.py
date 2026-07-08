"""Composite toolkit that aggregates several toolkits behind one interface.

The tool-calling agent sees the union of all tool schemas and dispatches each
tool call to the toolkit that owns it. This lets transactions, budgets, and
goals be developed as independent toolkits while the agent treats them as one.
"""

from typing import Any

from app.agents.tools.base import Toolkit
from app.core.logging import get_logger
from app.shared.types import UserId

logger = get_logger(__name__)


class CompositeToolkit:
    """Merges the schemas of several toolkits and routes calls by tool name."""

    def __init__(self, toolkits: list[Toolkit]) -> None:
        self._toolkits = toolkits
        self._by_name: dict[str, Toolkit] = {}
        for toolkit in toolkits:
            for schema in toolkit.schemas:
                name = schema["function"]["name"]
                if name in self._by_name:
                    raise ValueError(f"Duplicate tool name across toolkits: {name}")
                self._by_name[name] = toolkit

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [schema for toolkit in self._toolkits for schema in toolkit.schemas]

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: UserId) -> str:
        toolkit = self._by_name.get(name)
        if toolkit is None:
            raise ValueError(f"Unknown tool: {name}")
        return await toolkit.dispatch(name, arguments, user_id)
