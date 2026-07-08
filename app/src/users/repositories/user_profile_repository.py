"""Supabase-backed user-profile repository (data access only)."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import InfrastructureError
from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import parse_datetime, parse_optional_decimal
from app.shared.serialization import decimal_to_db
from app.shared.types import UserId

from ..constants import USER_PROFILES_TABLE
from ..interfaces import UserProfileRepositoryABC
from ..models import UserProfile, UserProfileUpdate

logger = get_logger(__name__)


class UserProfileRepository(UserProfileRepositoryABC):
    """Persists user profiles in Supabase via the database interface."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def get(self, user_id: UserId) -> UserProfile | None:
        config = QueryConfig(filters={"user_id": user_id}, limit=1)
        result = await self._db.select(USER_PROFILES_TABLE, config)
        if not result.data:
            return None
        return _row_to_profile(result.data[0])

    async def upsert(self, user_id: UserId, data: UserProfileUpdate) -> UserProfile:
        row: dict[str, Any] = {"user_id": user_id}
        if data.display_name is not None:
            row["display_name"] = data.display_name
        if data.monthly_income is not None:
            row["monthly_income"] = decimal_to_db(data.monthly_income)
        if data.savings_goal_percentage is not None:
            row["savings_goal_percentage"] = decimal_to_db(data.savings_goal_percentage)
        if data.onboarding_completed is not None:
            row["onboarding_completed"] = data.onboarding_completed

        result = await self._db.upsert(USER_PROFILES_TABLE, row, on_conflict="user_id")
        if not result.data:
            raise InfrastructureError(
                "User profile upsert returned no rows",
                code="USER_PROFILE_UPSERT_FAILED",
            )

        profile = _row_to_profile(result.data[0])
        logger.info("User profile updated", user_id=user_id)
        return profile


def _row_to_profile(row: dict[str, Any]) -> UserProfile:
    """Map a raw database row to a domain ``UserProfile``."""
    return UserProfile(
        user_id=str(row["user_id"]),
        display_name=row.get("display_name"),
        monthly_income=parse_optional_decimal(row.get("monthly_income")),
        savings_goal_percentage=parse_optional_decimal(row.get("savings_goal_percentage")),
        onboarding_completed=bool(row.get("onboarding_completed", False)),
        updated_at=parse_datetime(row.get("updated_at")) if row.get("updated_at") else None,
    )
