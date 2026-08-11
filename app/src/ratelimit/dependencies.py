"""Dependency injection wiring for the rate-limiting module."""

from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.shared.dependencies import DatabaseDep

from .interfaces import RateLimitRepositoryABC, RateLimitServiceABC
from .repositories.rate_limit_repository import RateLimitRepository
from .services.rate_limit_service import RateLimitService


def get_rate_limit_repository(db: DatabaseDep) -> RateLimitRepositoryABC:
    """Provide the rate-limit counter repository."""
    return RateLimitRepository(db)


def get_rate_limit_service(
    repository: Annotated[RateLimitRepositoryABC, Depends(get_rate_limit_repository)],
) -> RateLimitServiceABC:
    """Provide the rate-limit service, wired from env-tunable settings."""
    return RateLimitService(
        repository,
        per_minute=settings.RATE_LIMIT_CHAT_PER_MINUTE,
        per_day=settings.RATE_LIMIT_CHAT_PER_DAY,
        images_per_day=settings.RATE_LIMIT_IMAGES_PER_DAY,
        enabled=settings.RATE_LIMIT_ENABLED,
    )


RateLimitServiceDep = Annotated[RateLimitServiceABC, Depends(get_rate_limit_service)]
