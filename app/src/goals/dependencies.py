"""Dependency injection wiring for the goals module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep

from .interfaces import GoalRepositoryABC, GoalServiceABC
from .repositories.goal_repository import GoalRepository
from .services.goal_service import GoalService


def get_goal_repository(db: DatabaseDep) -> GoalRepositoryABC:
    """Provide the goal repository."""
    return GoalRepository(db)


def get_goal_service(
    repository: Annotated[GoalRepositoryABC, Depends(get_goal_repository)],
) -> GoalServiceABC:
    """Provide the goal service."""
    return GoalService(repository)


GoalServiceDep = Annotated[GoalServiceABC, Depends(get_goal_service)]
