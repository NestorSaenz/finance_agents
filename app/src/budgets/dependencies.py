"""Dependency injection wiring for the budgets module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep

from .interfaces import BudgetRepositoryABC, BudgetServiceABC, BudgetSpendingABC
from .repositories.budget_repository import BudgetRepository
from .services.budget_service import BudgetService
from .services.spending_provider import TransactionSpendingProvider


def get_budget_repository(db: DatabaseDep) -> BudgetRepositoryABC:
    """Provide the budget repository."""
    return BudgetRepository(db)


def get_budget_spending(db: DatabaseDep) -> BudgetSpendingABC:
    """Provide the spending provider (reads the transactions table)."""
    return TransactionSpendingProvider(db)


def get_budget_service(
    repository: Annotated[BudgetRepositoryABC, Depends(get_budget_repository)],
    spending: Annotated[BudgetSpendingABC, Depends(get_budget_spending)],
) -> BudgetServiceABC:
    """Provide the budget service."""
    return BudgetService(repository, spending)


BudgetServiceDep = Annotated[BudgetServiceABC, Depends(get_budget_service)]
