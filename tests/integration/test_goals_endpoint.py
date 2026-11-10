"""Integration tests for the /goals endpoints (service overridden)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import GoalNotFoundError
from app.main import app
from app.shared.clock import local_date
from app.shared.types import (
    CurrencyType,
    GoalId,
    GoalPlanClearMode,
    GoalPlanScope,
    GoalStatus,
    GoalType,
    UserId,
)
from app.src.goals.dependencies import get_goal_service
from app.src.goals.interfaces import GoalServiceABC
from app.src.goals.models import (
    Goal,
    GoalContribution,
    GoalContributionView,
    GoalCreate,
    GoalMonthLine,
    GoalPlanStatus,
    GoalProgress,
)
from app.src.users.dependencies import get_user_profile_service
from app.src.users.interfaces import UserProfileServiceABC
from app.src.users.models import UserProfile, UserProfileUpdate

BASE_URL = "/api/v1/goals"


def _goal(status: GoalStatus = GoalStatus.ACTIVE) -> Goal:
    return Goal(
        id="goal-1",
        user_id="demo-user",
        name="Viaje a Japón",
        description=None,
        goal_type=GoalType.SAVINGS,
        target_amount=Decimal("100000"),
        current_amount=Decimal("30000"),
        currency=CurrencyType.MXN,
        target_date=date(2025, 12, 31),
        monthly_contribution=None,
        status=status,
        priority=1,
        created_at=datetime(2024, 12, 1, tzinfo=UTC),
    )


def _status(
    goal_id: str, currency: CurrencyType, planned: str, saved: str, effective: str | None = None
) -> GoalPlanStatus:
    planned_amount, saved_amount = Decimal(planned), Decimal(saved)
    remaining = max(planned_amount - saved_amount, Decimal("0"))
    return GoalPlanStatus(
        goal_id=goal_id,
        goal_name=f"Meta {goal_id}",
        currency=currency,
        month=date(2026, 6, 1),
        planned=planned_amount,
        effective_planned=Decimal(effective) if effective is not None else planned_amount,
        contributed_gross=saved_amount,
        withdrawn=Decimal("10"),
        remaining=remaining,
        percentage=50.0,
        is_met=remaining == 0,
        goal_completed=False,
    )


class StubProfileService(UserProfileServiceABC):
    """Profile stub with a fixed timezone (or a failing read)."""

    def __init__(self, timezone: str = "America/Bogota", fail: bool = False) -> None:
        self._timezone = timezone
        self._fail = fail

    async def get_profile(self, user_id: str) -> UserProfile:
        if self._fail:
            raise httpx.ConnectError("down")
        return UserProfile(user_id=user_id, timezone=self._timezone)

    async def update_profile(self, user_id: str, data: UserProfileUpdate) -> UserProfile:
        return await self.get_profile(user_id)

    async def set_currency(self, user_id: str, code: str) -> UserProfile:
        return await self.get_profile(user_id)

    async def set_timezone(self, user_id: str, tz: str) -> UserProfile:
        return await self.get_profile(user_id)


class StubGoalService(GoalServiceABC):
    def __init__(self, found: bool = True) -> None:
        self.found = found
        self.contribution_dates: list[date | None] = []
        self.progress_dates: list[date | None] = []
        self.plan_calls: list[tuple[str, Decimal, date, GoalPlanScope]] = []
        self.clear_calls: list[tuple[str, date, GoalPlanClearMode]] = []
        self.status_calls: list[tuple[date, date, date | None]] = []
        self.history_calls: list[tuple[int, date | None, date | None]] = []

    async def create_goal(self, goal: GoalCreate, user_id: UserId) -> Goal:
        return _goal()

    async def get_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        return _goal()

    async def list_goals(
        self,
        user_id: UserId,
        *,
        page: int,
        page_size: int,
        as_of: date | None = None,
    ) -> tuple[list[Goal], int]:
        return [_goal()], 1

    async def contribute(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date | None = None,
    ) -> Goal:
        self.contribution_dates.append(contribution_date)
        return _goal(status=GoalStatus.COMPLETED)

    async def withdraw_from_goal(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        withdrawal_date: date,
    ) -> Goal:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        return _goal()

    async def set_goal_amount(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        on_date: date,
    ) -> Goal:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        return _goal()

    async def set_paused(
        self, goal_id: GoalId, user_id: UserId, paused: bool
    ) -> Goal:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        return _goal(status=GoalStatus.PAUSED if paused else GoalStatus.ACTIVE)

    async def set_plan(
        self,
        user_id: UserId,
        goal_id: GoalId,
        amount: Decimal,
        month: date,
        scope: GoalPlanScope,
    ) -> Decimal | None:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        self.plan_calls.append((goal_id, amount, month, scope))
        return amount

    async def clear_plan(
        self,
        user_id: UserId,
        goal_id: GoalId,
        month: date,
        mode: GoalPlanClearMode,
    ) -> Decimal | None:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        self.clear_calls.append((goal_id, month, mode))
        return Decimal("500") if mode == GoalPlanClearMode.VOLVER_AL_GENERAL else Decimal("0")

    async def get_plan_status(
        self,
        user_id: UserId,
        period_start: date,
        period_end: date,
        today: date | None = None,
    ) -> list[GoalPlanStatus]:
        self.status_calls.append((period_start, period_end, today))
        return [
            _status("g1", CurrencyType.MXN, "1000", "400"),
            _status("g2", CurrencyType.MXN, "500.50", "500.50", effective="0"),
            _status("g3", CurrencyType.USD, "100", "0", effective="80"),
        ]

    async def get_monthly_history(
        self,
        user_id: UserId,
        months: int = 6,
        to_month: date | None = None,
        today: date | None = None,
    ) -> list[GoalMonthLine]:
        self.history_calls.append((months, to_month, today))
        return [
            GoalMonthLine(
                goal_id="g1",
                goal_name="Viaje",
                currency=CurrencyType.MXN,
                month=date(2026, 6, 1),
                planned=None,
                saved=Decimal("100"),
                withdrawn=Decimal("0"),
                cumulative=Decimal("100"),
            ),
            GoalMonthLine(
                goal_id="g1",
                goal_name="Viaje",
                currency=CurrencyType.MXN,
                month=date(2026, 7, 1),
                planned=Decimal("500"),
                effective_planned=Decimal("300"),
                saved=Decimal("0"),
                withdrawn=Decimal("0"),
                cumulative=Decimal("100"),
            ),
        ]

    async def contributed_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> Decimal:
        return Decimal("1500")

    async def list_contributions_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[GoalContributionView]:
        return [
            GoalContributionView(
                goal_name="Viaje a Japón",
                amount=Decimal("5000"),
                contribution_date=date(2026, 6, 15),
            ),
            GoalContributionView(
                goal_name="Meta",
                amount=Decimal("2000"),
                contribution_date=date(2026, 6, 10),
            ),
        ]

    async def update_goal(
        self,
        goal_id: GoalId,
        user_id: UserId,
        *,
        name: str | None = None,
        target_amount: Decimal | None = None,
        target_date: date | None = None,
    ) -> Goal:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        return _goal()

    async def delete_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        if not self.found:
            raise GoalNotFoundError(goal_id)
        return _goal()

    async def list_contributions(
        self, goal_id: GoalId, user_id: UserId
    ) -> list[GoalContribution]:
        return []

    async def remove_contribution(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date | None = None,
    ) -> Goal | None:
        if not self.found:
            return None
        return _goal()

    async def get_progress(
        self, goal_id: GoalId, user_id: UserId, as_of: date | None = None
    ) -> GoalProgress:
        self.progress_dates.append(as_of)
        return GoalProgress(
            goal=_goal(),
            percentage=30.0,
            remaining=Decimal("70000"),
            is_completed=False,
            months_remaining=11,
            required_monthly_contribution=Decimal("6363.64"),
            on_track=True,
        )


def _client(
    service: GoalServiceABC, profiles: UserProfileServiceABC | None = None
) -> Iterator[TestClient]:
    app.dependency_overrides[get_goal_service] = lambda: service
    app.dependency_overrides[get_user_profile_service] = lambda: profiles or StubProfileService()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield from _client(StubGoalService())


class TestCrud:
    def test_create_goal(self, client: TestClient) -> None:
        # Goals are born at 0: the create request no longer accepts current_amount.
        response = client.post(
            BASE_URL,
            json={"name": "Viaje a Japón", "target_amount": 100000},
        )
        assert response.status_code == 200
        assert response.json()["id"] == "goal-1"

    def test_list_goals(self, client: TestClient) -> None:
        response = client.get(BASE_URL)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["total_contributed"] == "0"  # no period → not computed

    def test_list_goals_reports_contributed_for_period(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}?period=2026-06")
        assert response.status_code == 200
        assert response.json()["total_contributed"] == "1500"

    def test_list_contributions_returns_names_and_total(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/contributions?period=2026-06")
        assert response.status_code == 200
        body = response.json()
        # The literal /contributions path is NOT captured by /{goal_id}.
        assert [c["goal_name"] for c in body["contributions"]] == ["Viaje a Japón", "Meta"]
        assert body["total"] == "7000"  # 5000 + 2000

    def test_missing_goal_returns_404(self) -> None:
        gen = _client(StubGoalService(found=False))
        client = next(gen)
        try:
            response = client.get(f"{BASE_URL}/nope")
            assert response.status_code == 404
            assert response.json()["error"] == "GOAL_NOT_FOUND"
        finally:
            next(gen, None)

    def test_delete_goal(self, client: TestClient) -> None:
        response = client.delete(f"{BASE_URL}/goal-1")
        assert response.status_code == 200
        assert response.json()["id"] == "goal-1"

    def test_delete_missing_goal_returns_404(self) -> None:
        gen = _client(StubGoalService(found=False))
        client = next(gen)
        try:
            response = client.delete(f"{BASE_URL}/nope")
            assert response.status_code == 404
        finally:
            next(gen, None)


class TestProgressAndContribute:
    def test_progress(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/goal-1/progress")
        assert response.status_code == 200
        body = response.json()
        assert body["percentage"] == 30.0
        assert body["required_monthly_contribution"] == "6363.64"

    def test_contribute(self, client: TestClient) -> None:
        response = client.post(f"{BASE_URL}/goal-1/contribute", json={"amount": 5000})
        assert response.status_code == 200
        assert response.json()["status"] == "completed"


# 04:06 UTC on Oct 1 is still 23:06 on Sep 30 in Bogotá (Astrid's real case).
_FROZEN_UTC = datetime(2026, 10, 1, 4, 6, tzinfo=UTC)


@pytest.fixture
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """Freeze the route's clock at ``_FROZEN_UTC`` (the timezone conversion stays real)."""
    monkeypatch.setattr(
        "app.api.routes.goals.local_today", lambda tz: local_date(_FROZEN_UTC, tz)
    )


def _contribute(
    service: StubGoalService,
    profiles: UserProfileServiceABC,
    body: dict[str, object],
) -> None:
    for client in _client(service, profiles):
        response = client.post(f"{BASE_URL}/goal-1/contribute", json=body)
        assert response.status_code == 200


@pytest.mark.usefixtures("frozen_now")
class TestLocalDateDefaults:
    def test_contribute_without_date_uses_the_users_local_day(self) -> None:
        service = StubGoalService()

        _contribute(service, StubProfileService("America/Bogota"), {"amount": 5000})

        assert service.contribution_dates == [date(2026, 9, 30)]  # NOT the UTC Oct 1

    def test_contribute_with_explicit_date_keeps_it(self) -> None:
        service = StubGoalService()

        _contribute(
            service,
            StubProfileService("America/Bogota"),
            {"amount": 5000, "contribution_date": "2026-08-15"},
        )

        assert service.contribution_dates == [date(2026, 8, 15)]

    def test_timezone_ahead_of_utc_gets_its_own_day(self) -> None:
        service = StubGoalService()

        _contribute(service, StubProfileService("Asia/Tokyo"), {"amount": 5000})

        assert service.contribution_dates == [date(2026, 10, 1)]

    def test_profile_failure_falls_back_to_the_default_timezone(self) -> None:
        service = StubGoalService()

        _contribute(service, StubProfileService(fail=True), {"amount": 5000})

        assert service.contribution_dates == [date(2026, 9, 30)]  # DEFAULT_TIMEZONE = Bogotá

    def test_progress_is_evaluated_on_the_users_local_day(self) -> None:
        service = StubGoalService()
        for client in _client(service, StubProfileService("America/Bogota")):
            assert client.get(f"{BASE_URL}/goal-1/progress").status_code == 200

        assert service.progress_dates == [date(2026, 9, 30)]


@pytest.mark.usefixtures("frozen_now")
class TestPlanStatusEndpoint:
    def test_literal_path_is_not_captured_by_the_goal_id_route(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/plan-status")

        assert response.status_code == 200
        assert "statuses" in response.json()  # a GoalResponse would have had "id"

    def test_default_period_is_this_month_on_the_users_local_calendar(self) -> None:
        service = StubGoalService()
        for client in _client(service, StubProfileService("America/Bogota")):
            assert client.get(f"{BASE_URL}/plan-status").status_code == 200

        # 04:06 UTC on Oct 1 is still Sep 30 in Bogota: the month is September.
        assert service.status_calls == [(date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 30))]

    @pytest.mark.parametrize(
        ("period", "expected"),
        [
            ("mes_pasado", (date(2026, 8, 1), date(2026, 8, 31))),
            ("2026-02", (date(2026, 2, 1), date(2026, 2, 28))),
            ("2027-12", (date(2027, 12, 1), date(2027, 12, 31))),
        ],
    )
    def test_period_values(self, period: str, expected: tuple[date, date]) -> None:
        service = StubGoalService()
        for client in _client(service):
            assert client.get(f"{BASE_URL}/plan-status?period={period}").status_code == 200

        assert service.status_calls[0][:2] == expected

    def test_todo_returns_an_empty_list_without_calling_the_service(self) -> None:
        service = StubGoalService()
        for client in _client(service):
            body = client.get(f"{BASE_URL}/plan-status?period=todo").json()

        assert body == {
            "statuses": [],
            "total_planned": {},
            "total_effective_planned": {},
            "total_saved": {},
            "total_withdrawn": {},
        }
        assert service.status_calls == []

    def test_totals_are_grouped_by_currency_and_exact(self, client: TestClient) -> None:
        body = client.get(f"{BASE_URL}/plan-status?period=2026-06").json()

        assert [s["goal_id"] for s in body["statuses"]] == ["g1", "g2", "g3"]
        assert body["statuses"][0]["month"] == "2026-06"
        assert body["total_planned"] == {"MXN": "1500.50", "USD": "100"}
        assert body["total_effective_planned"] == {"MXN": "1000", "USD": "80"}
        assert body["total_saved"] == {"MXN": "900.50", "USD": "0"}
        assert body["total_withdrawn"] == {"MXN": "20", "USD": "10"}

    @pytest.mark.parametrize("period", ["2026-13", "2026-6", "junio", "0000-05", "este mes"])
    def test_invalid_period_is_a_422(self, client: TestClient, period: str) -> None:
        assert client.get(f"{BASE_URL}/plan-status", params={"period": period}).status_code == 422


@pytest.mark.usefixtures("frozen_now")
class TestMonthlyHistoryEndpoint:
    def test_literal_path_is_not_captured_by_the_goal_id_route(self, client: TestClient) -> None:
        response = client.get(f"{BASE_URL}/monthly")

        assert response.status_code == 200
        lines = response.json()["lines"]
        assert lines[0]["planned"] is None and lines[0]["effective_planned"] is None
        assert lines[1]["planned"] == "500"
        assert lines[1]["effective_planned"] == "300"  # capped at what the goal still lacked

    def test_defaults_to_six_months_ending_in_the_current_month(self) -> None:
        service = StubGoalService()
        for client in _client(service):
            assert client.get(f"{BASE_URL}/monthly").status_code == 200

        assert service.history_calls == [(6, None, date(2026, 9, 30))]

    def test_months_and_to_are_forwarded(self) -> None:
        service = StubGoalService()
        for client in _client(service):
            assert client.get(f"{BASE_URL}/monthly?months=3&to=2026-12").status_code == 200

        assert service.history_calls == [(3, date(2026, 12, 1), date(2026, 9, 30))]

    @pytest.mark.parametrize("query", ["months=0", "months=25", "to=2026-13", "to=hoy"])
    def test_invalid_query_is_a_422(self, client: TestClient, query: str) -> None:
        assert client.get(f"{BASE_URL}/monthly?{query}").status_code == 422


class TestPlanWriteEndpoints:
    def test_put_without_scope_is_a_422(self, client: TestClient) -> None:
        response = client.put(f"{BASE_URL}/goal-1/plans/2026-06", json={"amount": 750.5})

        assert response.status_code == 422

    def test_put_desde_mes(self) -> None:
        service = StubGoalService()
        for client in _client(service):
            response = client.put(
                f"{BASE_URL}/goal-1/plans/2026-06", json={"amount": 750.5, "scope": "desde_mes"}
            )

        assert response.status_code == 200
        assert response.json() == {"goal_id": "goal-1", "month": "2026-06", "planned_amount": "750.5"}
        assert service.plan_calls == [
            ("goal-1", Decimal("750.5"), date(2026, 6, 1), GoalPlanScope.DESDE_MES)
        ]

    def test_put_solo_mes_and_zero_amount(self) -> None:
        service = StubGoalService()
        for client in _client(service):
            response = client.put(
                f"{BASE_URL}/goal-1/plans/2026-06", json={"amount": 0, "scope": "solo_mes"}
            )

        assert response.status_code == 200
        assert service.plan_calls == [("goal-1", Decimal("0"), date(2026, 6, 1), GoalPlanScope.SOLO_MES)]

    @pytest.mark.parametrize(
        ("month", "body"),
        [
            ("2026-06", {"amount": -1}),
            ("2026-06", {"amount": "abc"}),
            ("2026-06", {}),
            ("2026-06", {"amount": 10, "scope": "siempre"}),
            ("2026-06", {"amount": 99999999999}),
            ("2026-13", {"amount": 10}),
            ("2026-6", {"amount": 10}),
            ("monthly", {"amount": 10}),
        ],
    )
    def test_put_validation_is_a_422(self, client: TestClient, month: str, body: dict[str, object]) -> None:
        assert client.put(f"{BASE_URL}/goal-1/plans/{month}", json=body).status_code == 422

    def test_put_on_a_missing_goal_is_a_404(self) -> None:
        for client in _client(StubGoalService(found=False)):
            response = client.put(
                f"{BASE_URL}/nope/plans/2026-06", json={"amount": 10, "scope": "solo_mes"}
            )

        assert response.status_code == 404
        assert response.json()["error"] == "GOAL_NOT_FOUND"

    def test_delete_defaults_to_volver_al_general(self) -> None:
        service = StubGoalService()
        for client in _client(service):
            response = client.delete(f"{BASE_URL}/goal-1/plans/2026-06")

        assert response.status_code == 200
        assert response.json() == {"goal_id": "goal-1", "month": "2026-06", "planned_amount": "500"}
        assert service.clear_calls == [("goal-1", date(2026, 6, 1), GoalPlanClearMode.VOLVER_AL_GENERAL)]

    def test_delete_with_mode(self) -> None:
        service = StubGoalService()
        for client in _client(service):
            response = client.delete(f"{BASE_URL}/goal-1/plans/2026-06?mode=terminar")

        assert response.json()["planned_amount"] == "0"
        assert service.clear_calls == [("goal-1", date(2026, 6, 1), GoalPlanClearMode.TERMINAR)]

    def test_delete_with_unknown_mode_is_a_422(self, client: TestClient) -> None:
        assert client.delete(f"{BASE_URL}/goal-1/plans/2026-06?mode=borrar").status_code == 422

    def test_delete_on_a_missing_goal_is_a_404(self) -> None:
        for client in _client(StubGoalService(found=False)):
            response = client.delete(f"{BASE_URL}/nope/plans/2026-06")

        assert response.status_code == 404

    def test_goal_routes_still_work_next_to_the_plan_routes(self, client: TestClient) -> None:
        assert client.get(f"{BASE_URL}/goal-1").json()["id"] == "goal-1"
        assert client.delete(f"{BASE_URL}/goal-1").json()["id"] == "goal-1"
