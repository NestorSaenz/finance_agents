"""Dependency injection wiring for the transactions module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep, EmbeddingDep, VectorStoreDep

from .interfaces import (
    TransactionCategorizerABC,
    TransactionRepositoryABC,
    TransactionServiceABC,
)
from .repositories.transaction_repository import TransactionRepository
from .services.semantic_categorizer import SemanticTransactionCategorizer
from .services.transaction_service import TransactionService


def get_transaction_repository(db: DatabaseDep) -> TransactionRepositoryABC:
    """Provide the transaction repository."""
    return TransactionRepository(db)


def get_transaction_categorizer(
    embedding: EmbeddingDep,
    vector_store: VectorStoreDep,
) -> TransactionCategorizerABC:
    """Provide the semantic transaction categorizer."""
    return SemanticTransactionCategorizer(embedding, vector_store)


def get_transaction_service(
    repository: Annotated[TransactionRepositoryABC, Depends(get_transaction_repository)],
    categorizer: Annotated[TransactionCategorizerABC, Depends(get_transaction_categorizer)],
) -> TransactionServiceABC:
    """Provide the transaction service."""
    return TransactionService(repository, categorizer)


TransactionServiceDep = Annotated[TransactionServiceABC, Depends(get_transaction_service)]
