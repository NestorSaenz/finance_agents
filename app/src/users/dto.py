"""Data Transfer Objects for the users API layer."""

from decimal import Decimal

from pydantic import BaseModel, Field

from .models import UserProfile


class OnboardingRequest(BaseModel):
    """Payload submitted when the user finishes (or skips) onboarding.

    Both figures are optional so the client can skip them; either way the
    profile is marked as onboarded so the wizard is not shown again.
    """

    display_name: str | None = Field(
        default=None, max_length=80, description="How the user wants to be addressed"
    )
    monthly_income: Decimal | None = Field(
        default=None, gt=0, description="Stated monthly income (reference figure)"
    )
    savings_goal_percentage: Decimal | None = Field(
        default=None, ge=0, le=100, description="Target % of income to save monthly"
    )


class UserProfileResponse(BaseModel):
    """Response body describing the user's profile / onboarding state."""

    display_name: str | None
    monthly_income: Decimal | None
    savings_goal_percentage: Decimal | None
    onboarding_completed: bool

    @classmethod
    def from_domain(cls, profile: UserProfile) -> "UserProfileResponse":
        return cls(
            display_name=profile.display_name,
            monthly_income=profile.monthly_income,
            savings_goal_percentage=profile.savings_goal_percentage,
            onboarding_completed=profile.onboarding_completed,
        )
