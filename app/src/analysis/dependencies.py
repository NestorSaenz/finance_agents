"""Dependency injection wiring for the analysis module."""

from typing import Annotated

from fastapi import Depends

from app.src.budgets.dependencies import BudgetServiceDep
from app.src.cards.dependencies import CreditCardServiceDep
from app.src.goals.dependencies import GoalServiceDep
from app.src.transactions.dependencies import TransactionServiceDep
from app.src.users.dependencies import UserProfileServiceDep

from .interfaces import AnalysisServiceABC
from .services.analysis_service import AnalysisService


def get_analysis_service(
    transactions: TransactionServiceDep,
    budgets: BudgetServiceDep,
    goals: GoalServiceDep,
    cards: CreditCardServiceDep,
    profiles: UserProfileServiceDep,
) -> AnalysisServiceABC:
    """Provide the analysis service, wired to the read-side domain services."""
    return AnalysisService(transactions, budgets, goals, cards, profiles)


AnalysisServiceDep = Annotated[AnalysisServiceABC, Depends(get_analysis_service)]
