"""Dependency injection wiring for the users module."""

from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DatabaseDep

from .interfaces import UserProfileRepositoryABC, UserProfileServiceABC
from .repositories.user_profile_repository import UserProfileRepository
from .services.user_profile_service import UserProfileService


def get_user_profile_repository(db: DatabaseDep) -> UserProfileRepositoryABC:
    """Provide the user-profile repository."""
    return UserProfileRepository(db)


def get_user_profile_service(
    repository: Annotated[
        UserProfileRepositoryABC, Depends(get_user_profile_repository)
    ],
) -> UserProfileServiceABC:
    """Provide the user-profile service."""
    return UserProfileService(repository)


UserProfileServiceDep = Annotated[
    UserProfileServiceABC, Depends(get_user_profile_service)
]
