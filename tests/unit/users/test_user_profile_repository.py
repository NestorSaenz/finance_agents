"""Unit tests for the Supabase-backed user-profile repository (DB mocked)."""

import pytest

from app.src.users.models import UserProfileUpdate
from app.src.users.repositories.user_profile_repository import UserProfileRepository
from tests.fakes import FakeDatabase

pytestmark = pytest.mark.asyncio


def _profile_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "user_id": "u1",
        "display_name": "Néstor",
        "monthly_income": "30000",
        "savings_goal_percentage": "20",
        "onboarding_completed": True,
        "currency": "GTQ",
        "timezone": "America/Guatemala",
        "updated_at": "2026-08-12T10:00:00+00:00",
    }
    row.update(overrides)
    return row


async def test_get_maps_currency_and_timezone() -> None:
    repo = UserProfileRepository(FakeDatabase(rows=[_profile_row()]))  # type: ignore[arg-type]

    profile = await repo.get("u1")

    assert profile is not None
    assert profile.currency == "GTQ"
    assert profile.timezone == "America/Guatemala"


async def test_get_leaves_currency_and_timezone_none_when_absent() -> None:
    row = _profile_row()
    del row["currency"]
    del row["timezone"]
    repo = UserProfileRepository(FakeDatabase(rows=[row]))  # type: ignore[arg-type]

    profile = await repo.get("u1")

    assert profile is not None
    assert profile.currency is None
    assert profile.timezone is None


async def test_upsert_persists_currency_and_timezone() -> None:
    db = FakeDatabase(rows=[_profile_row()])
    repo = UserProfileRepository(db)  # type: ignore[arg-type]

    profile = await repo.upsert(
        "u1", UserProfileUpdate(currency="USD", timezone="America/New_York")
    )

    # Round-trip: the written row carried both fields and they map back out.
    written = db.upserted[-1]
    assert written["currency"] == "USD"
    assert written["timezone"] == "America/New_York"
    assert profile.currency == "USD"
    assert profile.timezone == "America/New_York"


async def test_upsert_omits_currency_when_not_provided() -> None:
    db = FakeDatabase(rows=[_profile_row()])
    repo = UserProfileRepository(db)  # type: ignore[arg-type]

    await repo.upsert("u1", UserProfileUpdate(display_name="Ana"))

    written = db.upserted[-1]
    assert "currency" not in written
    assert "timezone" not in written
