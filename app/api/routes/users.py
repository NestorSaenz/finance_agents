"""User profile / onboarding endpoints."""

from fastapi import APIRouter

from app.core.logging import get_logger
from app.src.auth.dependencies import CurrentUserId
from app.src.users.dependencies import UserProfileServiceDep
from app.src.users.dto import OnboardingRequest, UserProfileResponse
from app.src.users.models import UserProfileUpdate

logger = get_logger(__name__)

router = APIRouter()


@router.get("/me/profile", response_model=UserProfileResponse)
async def get_my_profile(
    service: UserProfileServiceDep,
    user_id: CurrentUserId,
) -> UserProfileResponse:
    """Return the current user's profile and onboarding state."""
    profile = await service.get_profile(user_id)
    return UserProfileResponse.from_domain(profile)


@router.post("/me/onboarding", response_model=UserProfileResponse)
async def complete_onboarding(
    request: OnboardingRequest,
    service: UserProfileServiceDep,
    user_id: CurrentUserId,
) -> UserProfileResponse:
    """Store onboarding answers and mark the wizard as completed.

    ``monthly_income`` is optional (the client may skip it); the profile is
    always flagged as onboarded so the wizard is not shown again.
    """
    profile = await service.update_profile(
        user_id,
        UserProfileUpdate(
            display_name=request.display_name,
            monthly_income=request.monthly_income,
            savings_goal_percentage=request.savings_goal_percentage,
            currency=request.currency,
            timezone=request.timezone,
            onboarding_completed=True,
        ),
    )
    return UserProfileResponse.from_domain(profile)
