"""Dependency injection wiring for the credit-cards module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep

from .interfaces import (
    CardPaymentRepositoryABC,
    CreditCardRepositoryABC,
    CreditCardServiceABC,
    CreditCardSpendingABC,
)
from .repositories.card_payment_repository import CardPaymentRepository
from .repositories.credit_card_repository import CreditCardRepository
from .services.credit_card_service import CreditCardService
from .services.spending_provider import TransactionCardSpendingProvider


def get_credit_card_repository(db: DatabaseDep) -> CreditCardRepositoryABC:
    """Provide the credit-card repository."""
    return CreditCardRepository(db)


def get_card_payment_repository(db: DatabaseDep) -> CardPaymentRepositoryABC:
    """Provide the card-payment repository."""
    return CardPaymentRepository(db)


def get_card_spending(db: DatabaseDep) -> CreditCardSpendingABC:
    """Provide the card spending provider (reads the transactions table)."""
    return TransactionCardSpendingProvider(db)


def get_credit_card_service(
    repository: Annotated[CreditCardRepositoryABC, Depends(get_credit_card_repository)],
    payments: Annotated[CardPaymentRepositoryABC, Depends(get_card_payment_repository)],
    spending: Annotated[CreditCardSpendingABC, Depends(get_card_spending)],
) -> CreditCardServiceABC:
    """Provide the credit-card service."""
    return CreditCardService(repository, payments, spending)


CreditCardServiceDep = Annotated[
    CreditCardServiceABC, Depends(get_credit_card_service)
]
