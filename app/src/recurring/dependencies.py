"""Dependency injection wiring for the recurring-transactions module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep
from app.src.cards.dependencies import CreditCardServiceDep
from app.src.transactions.dependencies import TransactionServiceDep

from .interfaces import RecurringRepositoryABC, RecurringServiceABC
from .repositories.recurring_repository import RecurringRepository
from .services.recurring_service import RecurringService


def get_recurring_repository(db: DatabaseDep) -> RecurringRepositoryABC:
    """Provide the recurring-template repository."""
    return RecurringRepository(db)


def get_recurring_service(
    repository: Annotated[RecurringRepositoryABC, Depends(get_recurring_repository)],
    transactions: TransactionServiceDep,
    cards: CreditCardServiceDep,
) -> RecurringServiceABC:
    """Provide the recurring service (needs the transaction and card services)."""
    return RecurringService(repository, transactions, cards)


RecurringServiceDep = Annotated[RecurringServiceABC, Depends(get_recurring_service)]
