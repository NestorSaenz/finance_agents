"""Domain models for the users module."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


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
    updated_at: datetime | None = None


class UserProfileUpdate(BaseModel):
    """Fields that can be set during onboarding (all optional)."""

    display_name: str | None = Field(default=None, max_length=80)
    monthly_income: Decimal | None = Field(default=None, gt=0)
    savings_goal_percentage: Decimal | None = Field(default=None, ge=0, le=100)
    onboarding_completed: bool | None = None
