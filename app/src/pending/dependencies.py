"""Dependency injection wiring for the pending-actions module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep

from .interfaces import PendingActionRepositoryABC, PendingActionServiceABC
from .repositories.pending_action_repository import PendingActionRepository
from .services.pending_action_service import PendingActionService


def get_pending_action_repository(db: DatabaseDep) -> PendingActionRepositoryABC:
    """Provide the pending-action repository."""
    return PendingActionRepository(db)


def get_pending_action_service(
    repository: Annotated[PendingActionRepositoryABC, Depends(get_pending_action_repository)],
) -> PendingActionServiceABC:
    """Provide the pending-action service."""
    return PendingActionService(repository)


PendingActionServiceDep = Annotated[PendingActionServiceABC, Depends(get_pending_action_service)]
