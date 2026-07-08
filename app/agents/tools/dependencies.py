"""Dependency injection for agent tools."""

from typing import Annotated

from fastapi import Depends

from app.agents.tools.budget_tools import BudgetToolkit
from app.agents.tools.composite_toolkit import CompositeToolkit
from app.agents.tools.goal_tools import GoalToolkit
from app.agents.tools.transaction_tools import TransactionToolkit
from app.src.budgets.dependencies import BudgetServiceDep
from app.src.goals.dependencies import GoalServiceDep
from app.src.transactions.dependencies import TransactionServiceDep


def get_transaction_toolkit(service: TransactionServiceDep) -> TransactionToolkit:
    """Provide the transaction toolkit, wired to the transaction service."""
    return TransactionToolkit(service)


def get_budget_toolkit(service: BudgetServiceDep) -> BudgetToolkit:
    """Provide the budget toolkit, wired to the budget service."""
    return BudgetToolkit(service)


def get_goal_toolkit(service: GoalServiceDep) -> GoalToolkit:
    """Provide the goal toolkit, wired to the goal service."""
    return GoalToolkit(service)


def get_finance_toolkit(
    transactions: Annotated[TransactionToolkit, Depends(get_transaction_toolkit)],
    budgets: Annotated[BudgetToolkit, Depends(get_budget_toolkit)],
    goals: Annotated[GoalToolkit, Depends(get_goal_toolkit)],
) -> CompositeToolkit:
    """Provide the composite toolkit spanning transactions, budgets, and goals."""
    return CompositeToolkit([transactions, budgets, goals])


TransactionToolkitDep = Annotated[TransactionToolkit, Depends(get_transaction_toolkit)]
FinanceToolkitDep = Annotated[CompositeToolkit, Depends(get_finance_toolkit)]
