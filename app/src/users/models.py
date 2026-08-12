"""Domain models for the users module."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .constants import ISO_4217_CODES


class UserProfile(BaseModel):
    """Per-user profile holding onboarding state and reference figures."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str
    display_name: str | None = None
    monthly_income: Decimal | None = None
    # Target share of income to save each month (0-100). A percentage adapts to
    # variable income, unlike a fixed amount.
    savings_goal_percentage: Decimal | None = None
    onboarding_completed: bool = False
    # ISO-4217 code for how the user's amounts are labeled. Display only (no
    # conversion). Stored column is nullable; readers default it via the service.
    currency: str | None = None
    # IANA timezone (store-only for now; a later cut wires scheduling to it).
    timezone: str | None = None
    updated_at: datetime | None = None


class UserProfileUpdate(BaseModel):
    """Fields that can be set during onboarding (all optional)."""

    display_name: str | None = Field(default=None, max_length=80)
    monthly_income: Decimal | None = Field(default=None, gt=0)
    savings_goal_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    onboarding_completed: bool | None = None
    # Self-guarding: normalize + validate the ISO-4217 code here too, so no caller
    # (present or future) can ever persist a garbage currency that would mislabel
    # every amount. The service/DTO validate earlier for friendlier errors.
    currency: str | None = Field(default=None)
    # Self-guarding: validate the IANA zone here too, so no caller can persist a
    # garbage timezone that would resolve "today" in the wrong day.
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().upper()
        if code not in ISO_4217_CODES:
            raise ValueError(f"Unknown currency code: {value!r}")
        return code

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        tz = value.strip()
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"Unknown timezone: {value!r}") from e
        return tz
