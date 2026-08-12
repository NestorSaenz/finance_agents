"""Unit tests for the user-profile service."""

from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.exceptions import InvalidCurrencyError
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

        def pick(field: str, default: object = None) -> object:
            new_value = getattr(data, field)
            if new_value is not None:
                return new_value
            return getattr(existing, field) if existing else default

        profile = UserProfile(
            user_id=user_id,
            monthly_income=pick("monthly_income"),  # type: ignore[arg-type]
            onboarding_completed=bool(pick("onboarding_completed", False)),
            currency=pick("currency"),  # type: ignore[arg-type]
            timezone=pick("timezone"),  # type: ignore[arg-type]
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


@pytest.mark.asyncio
async def test_get_profile_defaults_currency_when_unset() -> None:
    service = UserProfileService(FakeProfileRepository())

    profile = await service.get_profile("u1")

    assert profile.currency == settings.DEFAULT_CURRENCY


@pytest.mark.asyncio
async def test_set_currency_persists_valid_code() -> None:
    repo = FakeProfileRepository()
    service = UserProfileService(repo)

    profile = await service.set_currency("u1", "GTQ")

    assert profile.currency == "GTQ"
    stored = await service.get_profile("u1")
    assert stored.currency == "GTQ"


@pytest.mark.asyncio
async def test_set_currency_normalizes_case_and_whitespace() -> None:
    service = UserProfileService(FakeProfileRepository())

    profile = await service.set_currency("u1", "  usd ")

    assert profile.currency == "USD"


@pytest.mark.asyncio
async def test_set_currency_rejects_unknown_code() -> None:
    service = UserProfileService(FakeProfileRepository())

    with pytest.raises(InvalidCurrencyError):
        await service.set_currency("u1", "XYZ")


@pytest.mark.asyncio
async def test_set_currency_preserves_existing_onboarding_state() -> None:
    repo = FakeProfileRepository()
    service = UserProfileService(repo)
    await service.update_profile("u1", UserProfileUpdate(onboarding_completed=True))

    await service.set_currency("u1", "MXN")

    stored = await service.get_profile("u1")
    assert stored.onboarding_completed is True
    assert stored.currency == "MXN"
