"""Agent tools for interacting with external services.

These tools provide the agents with capabilities to:
- Query and modify transactions
- Manage budgets
- Track financial goals
- Generate embeddings and search vectors
"""

from app.agents.tools.budget_tools import (
    check_budget_status,
    create_budget,
    get_budget_alerts,
)
from app.agents.tools.goal_tools import create_goal, get_goal_progress, update_goal
from app.agents.tools.transaction_tools import (
    categorize_transaction,
    get_transaction_summary,
    query_transactions,
)

__all__ = [
    # Transaction tools
    "query_transactions",
    "categorize_transaction",
    "get_transaction_summary",
    # Budget tools
    "create_budget",
    "check_budget_status",
    "get_budget_alerts",
    # Goal tools
    "create_goal",
    "update_goal",
    "get_goal_progress",
]
