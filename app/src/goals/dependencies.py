"""Dependency injection wiring for the goals module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep

from .interfaces import (
    ContributionMonthsProviderABC,
    GoalContributionRepositoryABC,
    GoalPlanRepositoryABC,
    GoalRepositoryABC,
    GoalServiceABC,
)
from .repositories.goal_contribution_repository import GoalContributionRepository
from .repositories.goal_plan_repository import GoalPlanRepository
from .repositories.goal_repository import GoalRepository
from .services.contribution_months_provider import ContributionMonthsProvider
from .services.goal_service import GoalService


def get_goal_repository(db: DatabaseDep) -> GoalRepositoryABC:
    """Provide the goal repository."""
    return GoalRepository(db)


def get_goal_contribution_repository(db: DatabaseDep) -> GoalContributionRepositoryABC:
    """Provide the goal-contribution repository."""
    return GoalContributionRepository(db)


def get_goal_plan_repository(db: DatabaseDep) -> GoalPlanRepositoryABC:
    """Provide the goal-plan repository."""
    return GoalPlanRepository(db)


def get_contribution_months_provider(
    db: DatabaseDep,
    contributions: Annotated[
        GoalContributionRepositoryABC, Depends(get_goal_contribution_repository)
    ],
) -> ContributionMonthsProviderABC:
    """Provide the gross-contributions-per-month provider."""
    return ContributionMonthsProvider(db, contributions)


def get_goal_service(
    repository: Annotated[GoalRepositoryABC, Depends(get_goal_repository)],
    contributions: Annotated[
        GoalContributionRepositoryABC, Depends(get_goal_contribution_repository)
    ],
    plans: Annotated[GoalPlanRepositoryABC, Depends(get_goal_plan_repository)],
    months: Annotated[
        ContributionMonthsProviderABC, Depends(get_contribution_months_provider)
    ],
) -> GoalServiceABC:
    """Provide the goal service."""
    return GoalService(repository, contributions, plans, months)


GoalServiceDep = Annotated[GoalServiceABC, Depends(get_goal_service)]
