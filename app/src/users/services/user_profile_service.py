"""User-profile use cases (business logic)."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.core.exceptions import InvalidCurrencyError, InvalidTimezoneError
from app.core.logging import get_logger
from app.shared.types import UserId

from ..constants import ISO_4217_CODES
from ..interfaces import UserProfileRepositoryABC, UserProfileServiceABC
from ..models import UserProfile, UserProfileUpdate

logger = get_logger(__name__)


class UserProfileService(UserProfileServiceABC):
    """Orchestrates reading and updating the user's profile."""

    def __init__(self, repository: UserProfileRepositoryABC) -> None:
        self._repository = repository

    async def get_profile(self, user_id: UserId) -> UserProfile:
        profile = await self._repository.get(user_id)
        # First access: report an empty, not-yet-onboarded profile without
        # writing a row (kept lazy; the row is created on the first update).
        if profile is None:
            profile = UserProfile(user_id=user_id)
        # Every consumer always gets a display currency: fall back to the app
        # default when none is stored (the stored column stays nullable).
        if profile.currency is None:
            profile.currency = settings.DEFAULT_CURRENCY
        # Same for the timezone: always hand back a valid IANA string so callers
        # can resolve "today" in the user's local day without extra guards.
        if profile.timezone is None:
            profile.timezone = settings.DEFAULT_TIMEZONE
        return profile

    async def update_profile(
        self, user_id: UserId, data: UserProfileUpdate
    ) -> UserProfile:
        return await self._repository.upsert(user_id, data)

    async def set_currency(self, user_id: UserId, code: str) -> UserProfile:
        normalized = code.strip().upper()
        if normalized not in ISO_4217_CODES:
            raise InvalidCurrencyError(normalized)
        profile = await self._repository.upsert(
            user_id, UserProfileUpdate(currency=normalized)
        )
        logger.info("User currency set", user_id=user_id, currency=normalized)
        return profile

    async def set_timezone(self, user_id: UserId, tz: str) -> UserProfile:
        normalized = tz.strip()
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise InvalidTimezoneError(normalized) from e
        profile = await self._repository.upsert(
            user_id, UserProfileUpdate(timezone=normalized)
        )
        logger.info("User timezone set", user_id=user_id, timezone=normalized)
        return profile
