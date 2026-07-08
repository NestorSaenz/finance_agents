"""User-profile use cases (business logic)."""

from app.core.logging import get_logger
from app.shared.types import UserId

from ..interfaces import UserProfileRepositoryABC, UserProfileServiceABC
from ..models import UserProfile, UserProfileUpdate

logger = get_logger(__name__)


class UserProfileService(UserProfileServiceABC):
    """Orchestrates reading and updating the user's profile."""

    def __init__(self, repository: UserProfileRepositoryABC) -> None:
        self._repository = repository

    async def get_profile(self, user_id: UserId) -> UserProfile:
        profile = await self._repository.get(user_id)
        if profile is not None:
            return profile
        # First access: report an empty, not-yet-onboarded profile without
        # writing a row (kept lazy; the row is created on the first update).
        return UserProfile(user_id=user_id)

    async def update_profile(
        self, user_id: UserId, data: UserProfileUpdate
    ) -> UserProfile:
        return await self._repository.upsert(user_id, data)
