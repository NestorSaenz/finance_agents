"""Unit tests for the user-profile service."""

from decimal import Decimal

import pytest

from app.shared.types import UserId
from app.src.users.interfaces import UserProfileRepositoryABC
from app.src.users.models import UserProfile, UserProfileUpdate
from app.src.users.services.user_profile_service import UserProfileService


class FakeProfileRepository(UserProfileRepositoryABC):
    def __init__(self) -> None:
        self.store: dict[str, UserProfile] = {}

    async def get(self, user_id: UserId) -> UserProfile | None:
        return self.store.get(user_id)

    async def upsert(self, user_id: UserId, data: UserProfileUpdate) -> UserProfile:
        existing = self.store.get(user_id)
        profile = UserProfile(
            user_id=user_id,
            monthly_income=(
                data.monthly_income
                if data.monthly_income is not None
                else (existing.monthly_income if existing else None)
            ),
            onboarding_completed=(
                data.onboarding_completed
                if data.onboarding_completed is not None
                else (existing.onboarding_completed if existing else False)
            ),
        )
        self.store[user_id] = profile
        return profile


@pytest.mark.asyncio
async def test_get_profile_returns_empty_when_missing() -> None:
    service = UserProfileService(FakeProfileRepository())

    profile = await service.get_profile("u1")

    assert profile.user_id == "u1"
    assert profile.onboarding_completed is False
    assert profile.monthly_income is None


@pytest.mark.asyncio
async def test_get_profile_does_not_persist_on_read() -> None:
    repo = FakeProfileRepository()
    service = UserProfileService(repo)

    await service.get_profile("u1")

    assert repo.store == {}


@pytest.mark.asyncio
async def test_update_profile_persists_fields() -> None:
    repo = FakeProfileRepository()
    service = UserProfileService(repo)

    profile = await service.update_profile(
        "u1",
        UserProfileUpdate(monthly_income=Decimal("30000"), onboarding_completed=True),
    )

    assert profile.monthly_income == Decimal("30000")
    assert profile.onboarding_completed is True
    stored = await service.get_profile("u1")
    assert stored.onboarding_completed is True
