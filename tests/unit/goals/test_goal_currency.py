"""A new goal's currency: explicit, else the user's profile currency, else the app default."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
import structlog.testing

from app.core.config import settings
from app.core.exceptions import DatabaseQueryError, InfrastructureError
from app.shared.types import CurrencyType, GoalId, GoalStatus, GoalType, UserId
from app.src.goals.currency import default_goal_currency
from app.src.goals.dto import GoalCreateRequest
from app.src.goals.interfaces import GoalRepositoryABC
from app.src.goals.models import Goal, GoalCreate
from app.src.goals.repositories.goal_repository import GoalRepository
from app.src.goals.services.contribution_months_provider import ContributionMonthsProvider
from app.src.goals.services.goal_service import GoalService
from tests.fakes import (
    FakeDatabase,
    FakeProfileService,
    InMemoryContributionLedger,
    InMemoryGoalPlanRepository,
    RpcFailingDatabase,
)

pytestmark = pytest.mark.asyncio


class CapturingRepository(GoalRepositoryABC):
    def __init__(self) -> None:
        self.created: list[GoalCreate] = []

    async def create(self, goal: GoalCreate, user_id: UserId) -> Goal:
        self.created.append(goal)
        assert goal.currency is not None  # the service always resolves it
        return Goal(
            id="g1", user_id=user_id, name=goal.name, description=None, goal_type=GoalType.SAVINGS,
            target_amount=goal.target_amount, current_amount=Decimal("0"), currency=goal.currency,
            target_date=None, monthly_contribution=None, status=GoalStatus.ACTIVE, priority=1,
            created_at=datetime(2026, 11, 1, tzinfo=UTC),
        )

    async def get_by_id(self, goal_id: GoalId, user_id: UserId) -> Goal | None:
        raise NotImplementedError

    async def list_page(self, user_id: UserId, *, limit: int, offset: int) -> list[Goal]:
        raise NotImplementedError

    async def count(self, user_id: UserId) -> int:
        raise NotImplementedError

    async def update(self, goal_id: GoalId, user_id: UserId, data: dict[str, Any]) -> Goal:
        raise NotImplementedError

    async def delete(self, goal_id: GoalId, user_id: UserId) -> None:
        raise NotImplementedError


def _service(profiles: FakeProfileService) -> tuple[GoalService, CapturingRepository]:
    repo, ledger = CapturingRepository(), InMemoryContributionLedger()
    service = GoalService(
        repo,
        ledger,
        InMemoryGoalPlanRepository(),
        ContributionMonthsProvider(RpcFailingDatabase(), ledger),  # type: ignore[arg-type]
        profiles,  # type: ignore[arg-type]
    )
    return service, repo


def _new(currency: CurrencyType | None = None) -> GoalCreate:
    return GoalCreate(name="Viaje", target_amount=Decimal("1000"), currency=currency)


async def test_without_a_currency_the_profile_currency_is_used() -> None:
    service, repo = _service(FakeProfileService("USD"))

    created = await service.create_goal(_new(), "u1")

    assert created.currency == CurrencyType.USD
    assert repo.created[0].currency == CurrencyType.USD


async def test_without_a_profile_currency_the_app_default_is_used() -> None:
    service, _ = _service(FakeProfileService(None))

    assert (await service.create_goal(_new(), "u1")).currency == CurrencyType(settings.DEFAULT_CURRENCY)
    assert (await service.create_goal(_new(), "u1")).currency == CurrencyType.COP


async def test_an_explicit_currency_is_respected() -> None:
    service, _ = _service(FakeProfileService("COP"))

    assert (await service.create_goal(_new(CurrencyType.EUR), "u1")).currency == CurrencyType.EUR


async def test_the_default_is_not_frozen_at_import(monkeypatch: pytest.MonkeyPatch) -> None:
    service, _ = _service(FakeProfileService(None))
    monkeypatch.setattr(settings, "DEFAULT_CURRENCY", "USD")

    assert (await service.create_goal(_new(), "u1")).currency == CurrencyType.USD
    assert _new().currency is None  # the model itself carries no frozen default
    assert GoalCreateRequest(name="x", target_amount=Decimal("1")).currency is None


@pytest.mark.parametrize(
    "profiles",
    [
        FakeProfileService("BRL"),  # a valid ISO code the goals module doesn't support
        FakeProfileService(fail=DatabaseQueryError("select", "down")),
        FakeProfileService(fail=httpx.ConnectError("down")),
    ],
)
async def test_unsupported_or_unreadable_profile_falls_back_to_the_app_default(
    profiles: FakeProfileService,
) -> None:
    service, _ = _service(profiles)

    assert (await service.create_goal(_new(), "u1")).currency == CurrencyType.COP


async def test_the_repository_refuses_an_unresolved_currency_instead_of_defaulting() -> None:
    db = FakeDatabase()
    repo = GoalRepository(db)  # type: ignore[arg-type]

    with pytest.raises(InfrastructureError):
        await repo.create(_new(), "u1")

    assert db.inserted == []  # nothing written with a made-up default


async def test_the_repository_writes_the_resolved_currency() -> None:
    db = FakeDatabase()
    repo = GoalRepository(db)  # type: ignore[arg-type]

    await repo.create(_new(CurrencyType.USD), "u1")

    assert db.inserted[0]["currency"] == "USD"


async def test_an_unsupported_default_currency_falls_back_to_cop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "DEFAULT_CURRENCY", "PEN")
    service, _ = _service(FakeProfileService(None))

    with structlog.testing.capture_logs() as logs:
        created = await service.create_goal(_new(), "u1")

    assert created.currency == CurrencyType.COP  # no error
    assert any(log["event"].startswith("Unsupported DEFAULT_CURRENCY") for log in logs)
    assert default_goal_currency() == CurrencyType.COP


@pytest.mark.parametrize("code", ["PEN", "ARS"])
async def test_an_unsupported_profile_currency_is_logged(code: str) -> None:
    service, _ = _service(FakeProfileService(code))

    with structlog.testing.capture_logs() as logs:
        created = await service.create_goal(_new(), "u1")

    assert created.currency == CurrencyType.COP
    warning = next(log for log in logs if log["event"] == "Unsupported profile currency for goals")
    assert warning["currency"] == code and warning["log_level"] == "warning"
