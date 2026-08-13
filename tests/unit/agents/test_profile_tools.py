"""Unit tests for the profile toolkit (service mocked)."""

from decimal import Decimal

import pytest

from app.agents.tools.profile_tools import (
    SET_CURRENCY_TOOL,
    SET_TIMEZONE_TOOL,
    UPDATE_PROFILE_TOOL,
    ProfileToolkit,
)
from app.core.exceptions import InvalidCurrencyError, InvalidTimezoneError
from app.shared.types import UserId
from app.src.users.interfaces import UserProfileServiceABC
from app.src.users.models import UserProfile, UserProfileUpdate

pytestmark = pytest.mark.asyncio


class FakeProfileService(UserProfileServiceABC):
    """Records set_currency/set_timezone calls; validates against tiny known sets."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.tz_calls: list[tuple[str, str]] = []
        self.updates: list[tuple[str, UserProfileUpdate]] = []

    async def get_profile(self, user_id: UserId) -> UserProfile:
        return UserProfile(user_id=user_id)

    async def update_profile(
        self, user_id: UserId, data: UserProfileUpdate
    ) -> UserProfile:
        self.updates.append((user_id, data))
        # Echo the applied fields back (partial update semantics).
        return UserProfile(
            user_id=user_id,
            display_name=data.display_name,
            monthly_income=data.monthly_income,
            savings_goal_percentage=data.savings_goal_percentage,
        )

    async def set_currency(self, user_id: UserId, code: str) -> UserProfile:
        normalized = code.strip().upper()
        self.calls.append((user_id, normalized))
        if normalized not in {"GTQ", "USD", "COP"}:
            raise InvalidCurrencyError(normalized)
        return UserProfile(user_id=user_id, currency=normalized)

    async def set_timezone(self, user_id: UserId, tz: str) -> UserProfile:
        normalized = tz.strip()
        self.tz_calls.append((user_id, normalized))
        if normalized not in {"America/Bogota", "America/Mexico_City"}:
            raise InvalidTimezoneError(normalized)
        return UserProfile(user_id=user_id, timezone=normalized)


async def test_valid_currency_returns_confirmation() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    result = await toolkit.dispatch(SET_CURRENCY_TOOL, {"currency": "GTQ"}, "u1")

    assert result == "✅ Listo, usaré GTQ para tus montos."
    assert service.calls == [("u1", "GTQ")]


async def test_invalid_currency_returns_friendly_message() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    result = await toolkit.dispatch(SET_CURRENCY_TOOL, {"currency": "XYZ"}, "u1")

    assert result == "No reconozco esa moneda; dime el país o el código, p. ej. GTQ."


async def test_empty_currency_returns_friendly_message() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    result = await toolkit.dispatch(SET_CURRENCY_TOOL, {}, "u1")

    assert "No reconozco esa moneda" in result
    assert service.calls == []


async def test_user_id_from_model_arguments_is_ignored() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    # A user_id smuggled into the model arguments must NOT override the
    # authenticated one bound at dispatch time.
    await toolkit.dispatch(
        SET_CURRENCY_TOOL, {"currency": "USD", "user_id": "attacker"}, "u1"
    )

    assert service.calls == [("u1", "USD")]


async def test_unknown_tool_raises() -> None:
    toolkit = ProfileToolkit(FakeProfileService())

    with pytest.raises(ValueError, match="Unknown profile tool"):
        await toolkit.dispatch("nope", {}, "u1")


async def test_valid_timezone_returns_confirmation() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    result = await toolkit.dispatch(
        SET_TIMEZONE_TOOL, {"timezone": "America/Bogota"}, "u1"
    )

    assert result == "✅ Listo, usaré tu zona America/Bogota para las fechas."
    assert service.tz_calls == [("u1", "America/Bogota")]


async def test_invalid_timezone_returns_friendly_message() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    result = await toolkit.dispatch(SET_TIMEZONE_TOOL, {"timezone": "Mars/Phobos"}, "u1")

    assert result == "No reconozco esa zona; dime tu ciudad, p. ej. 'Bogotá'."


async def test_empty_timezone_returns_friendly_message() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    result = await toolkit.dispatch(SET_TIMEZONE_TOOL, {}, "u1")

    assert "No reconozco esa zona" in result
    assert service.tz_calls == []


async def test_timezone_user_id_from_arguments_is_ignored() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    await toolkit.dispatch(
        SET_TIMEZONE_TOOL,
        {"timezone": "America/Mexico_City", "user_id": "attacker"},
        "u1",
    )

    assert service.tz_calls == [("u1", "America/Mexico_City")]


async def test_update_profile_sets_only_given_fields() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    result = await toolkit.dispatch(
        UPDATE_PROFILE_TOOL, {"display_name": "Néstor", "savings_goal_percentage": 30}, "u1"
    )

    user_id, data = service.updates[0]
    assert user_id == "u1"
    assert data.display_name == "Néstor"
    assert data.savings_goal_percentage == Decimal("30")
    assert data.monthly_income is None  # not touched
    # Never flips onboarding_completed on a settings edit.
    assert data.onboarding_completed is None
    assert "Néstor" in result and "30%" in result


async def test_update_profile_sets_income() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    await toolkit.dispatch(UPDATE_PROFILE_TOOL, {"monthly_income": 5000000}, "u1")

    _user, data = service.updates[0]
    assert data.monthly_income == Decimal("5000000")


async def test_update_profile_no_fields_asks() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    result = await toolkit.dispatch(UPDATE_PROFILE_TOOL, {}, "u1")

    assert not service.updates
    assert "¿qué quieres cambiar" in result.lower()


async def test_update_profile_rejects_invalid_income() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    # Income must be > 0; the pydantic ValidationError is caught → friendly message.
    result = await toolkit.dispatch(UPDATE_PROFILE_TOOL, {"monthly_income": 0}, "u1")

    assert not service.updates
    assert "mayor a 0" in result.lower()


async def test_update_profile_rejects_out_of_range_savings() -> None:
    service = FakeProfileService()
    toolkit = ProfileToolkit(service)

    result = await toolkit.dispatch(
        UPDATE_PROFILE_TOOL, {"savings_goal_percentage": 150}, "u1"
    )

    assert not service.updates
    assert "entre 0 y 100" in result.lower()
