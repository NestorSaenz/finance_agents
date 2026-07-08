"""Contracts (ABCs) for the users module."""

from abc import ABC, abstractmethod

from app.shared.types import UserId

from .models import UserProfile, UserProfileUpdate


class UserProfileRepositoryABC(ABC):
    """Contract for user-profile persistence (data access only)."""

    @abstractmethod
    async def get(self, user_id: UserId) -> UserProfile | None:
        """Return the profile for ``user_id`` or ``None`` if it does not exist."""

    @abstractmethod
    async def upsert(self, user_id: UserId, data: UserProfileUpdate) -> UserProfile:
        """Create or update a user's profile and return it."""


class UserProfileServiceABC(ABC):
    """Contract for user-profile use cases (business logic)."""

    @abstractmethod
    async def get_profile(self, user_id: UserId) -> UserProfile:
        """Return the user's profile, creating an empty one on first access."""

    @abstractmethod
    async def update_profile(
        self, user_id: UserId, data: UserProfileUpdate
    ) -> UserProfile:
        """Apply onboarding fields to the user's profile and return it."""
