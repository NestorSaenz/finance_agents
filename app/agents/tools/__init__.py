"""Agent tools for interacting with application services (LLM tool-calling).

Each toolkit wraps a domain service and exposes OpenAI-format tool schemas plus
a ``dispatch`` method. The ``CompositeToolkit`` aggregates them so the agent sees
one unified toolset. ``user_id`` is always bound from the auth context at
dispatch time, never taken from the model.
"""

from app.agents.tools.base import Toolkit
from app.agents.tools.budget_tools import BUDGET_TOOL_SCHEMAS, BudgetToolkit
from app.agents.tools.composite_toolkit import CompositeToolkit
from app.agents.tools.goal_tools import GOAL_TOOL_SCHEMAS, GoalToolkit
from app.agents.tools.transaction_tools import (
    TRANSACTION_TOOL_SCHEMAS,
    TransactionToolkit,
)

__all__ = [
    "Toolkit",
    "CompositeToolkit",
    "TransactionToolkit",
    "BudgetToolkit",
    "GoalToolkit",
    "TRANSACTION_TOOL_SCHEMAS",
    "BUDGET_TOOL_SCHEMAS",
    "GOAL_TOOL_SCHEMAS",
]
