"""Unit tests for the goal-plan tools (set/clear), create_goal's monthly plan and query_goals' plan lines."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.agents.nodes.action_claims import (
    MUTATING_TOOLS,
    READ_ONLY_TOOLS,
    is_write_attempt,
    is_write_refused,
)
from app.agents.tools.goal_tools import GOAL_TOOL_SCHEMAS, GoalToolkit
from app.agents.tools.names import CLEAR_GOAL_PLAN_TOOL, SET_GOAL_PLAN_TOOL
from app.core.exceptions import InvalidPlanPeriodError
from app.shared.clock import bound_today
from app.shared.turn import TurnContext, bound_turn
from app.shared.types import (
    CurrencyType,
    GoalPlanClearMode,
    GoalPlanScope,
    GoalStatus,
)
from app.src.goals.models import GoalMonthLine, GoalPlanStatus, GoalProgress
from tests.unit.agents.test_budget_goal_tools import FakeGoalService, _goal

D = Decimal
TODAY = date(2026, 11, 9)
UUID_LIKE = "9b1c2d3e-aaaa-bbbb-cccc-0123456789ab"


class PlanGoalService(FakeGoalService):
    """FakeGoalService with a recording, configurable planning surface."""

    def __init__(
        self,
        *args: object,
        statuses: list[GoalPlanStatus] | None = None,
        history: list[GoalMonthLine] | None = None,
        suggested: Decimal | None = None,
        plan_error: Exception | None = None,
        resolved: Decimal | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.set_calls: list[tuple[str, Decimal, date, GoalPlanScope]] = []
        self.clear_calls: list[tuple[str, date, GoalPlanClearMode]] = []
        self.status_calls: list[tuple[date, date]] = []
        self.history_calls: list[tuple[int, date | None]] = []
        self._statuses = statuses or []
        self._history = history or []
        self._suggested = suggested
        self._plan_error = plan_error
        self._resolved = resolved
        self.created_at = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)

    async def create_goal(self, goal, user_id):  # type: ignore[no-untyped-def]
        self.created.append((goal, user_id))
        return _goal(id="new", name=goal.name, created_at=self.created_at)

    async def list_goals(self, user_id, *, page, page_size, as_of=None):  # type: ignore[no-untyped-def]
        start = (page - 1) * page_size
        return self._goals[start : start + page_size], len(self._goals)

    async def set_plan(self, user_id, goal_id, amount, month, scope):  # type: ignore[no-untyped-def]
        if self._plan_error:
            raise self._plan_error
        self.set_calls.append((goal_id, amount, month, scope))
        return self._resolved if self._resolved is not None else amount

    async def clear_plan(self, user_id, goal_id, month, mode):  # type: ignore[no-untyped-def]
        if self._plan_error:
            raise self._plan_error
        self.clear_calls.append((goal_id, month, mode))
        return self._resolved

    async def get_plan_status(self, user_id, period_start, period_end, today=None):  # type: ignore[no-untyped-def]
        self.status_calls.append((period_start, period_end))
        return self._statuses

    async def get_monthly_history(self, user_id, months=6, to_month=None, today=None):  # type: ignore[no-untyped-def]
        self.history_calls.append((months, to_month))
        return self._history

    async def get_progress(self, goal_id, user_id, as_of=None):  # type: ignore[no-untyped-def]
        goal = next(g for g in self._goals if g.id == goal_id)
        return GoalProgress(
            goal=goal,
            percentage=25.0,
            remaining=D("75000"),
            is_completed=False,
            months_remaining=None,
            required_monthly_contribution=self._suggested,
            on_track=True,
        )


def _status(
    goal_id: str = "g1",
    *,
    planned: str = "500000",
    saved: str = "200000",
    withdrawn: str = "0",
    effective: str | None = None,
    remaining: str | None = None,
    currency: CurrencyType = CurrencyType.MXN,
    percentage: float = 40.0,
) -> GoalPlanStatus:
    planned_d = D(planned)
    left = D(remaining) if remaining is not None else max(planned_d - D(saved), D("0"))
    return GoalPlanStatus(
        goal_id=goal_id,
        goal_name="x",
        currency=currency,
        month=date(2026, 11, 1),
        planned=planned_d,
        effective_planned=D(effective) if effective is not None else planned_d,
        contributed_gross=D(saved),
        withdrawn=D(withdrawn),
        remaining=left,
        percentage=percentage,
        is_met=left == 0,
        goal_completed=False,
    )


def _service(**kwargs: object) -> PlanGoalService:
    goals = kwargs.pop("goals", None) or [_goal(id=UUID_LIKE, name="Vacaciones playa")]
    return PlanGoalService(goals=goals, **kwargs)  # type: ignore[arg-type]


async def _dispatch(service: PlanGoalService, name: str, args: dict[str, object]) -> str:
    with bound_today(TODAY):
        return await GoalToolkit(service).dispatch(name, args, "u1")


class TestRegistration:
    def test_schemas_expose_the_new_tools(self) -> None:
        names = {s["function"]["name"] for s in GOAL_TOOL_SCHEMAS}
        assert {SET_GOAL_PLAN_TOOL, CLEAR_GOAL_PLAN_TOOL} <= names

    def test_new_tools_are_mutating_and_not_read_only(self) -> None:
        assert {SET_GOAL_PLAN_TOOL, CLEAR_GOAL_PLAN_TOOL} <= MUTATING_TOOLS
        assert not ({SET_GOAL_PLAN_TOOL, CLEAR_GOAL_PLAN_TOOL} & READ_ONLY_TOOLS)

    def test_scope_and_mode_are_required(self) -> None:
        by_name = {s["function"]["name"]: s["function"]["parameters"] for s in GOAL_TOOL_SCHEMAS}
        assert "scope" in by_name[SET_GOAL_PLAN_TOOL]["required"]
        assert "mode" in by_name[CLEAR_GOAL_PLAN_TOOL]["required"]

    def test_refusals_are_not_counted_as_writes(self) -> None:
        question = "¿Confirmas que quieres poner el plan de septiembre 2026 que ya pasó?"
        assert is_write_refused(SET_GOAL_PLAN_TOOL, question)
        assert is_write_refused(CLEAR_GOAL_PLAN_TOOL, "No encontré una meta llamada 'x'.")
        assert is_write_attempt(SET_GOAL_PLAN_TOOL, "✅ Plan de X: $5 (solo noviembre 2026).")


class TestSetGoalPlan:
    async def test_solo_mes_for_a_named_month(self) -> None:
        service = _service()

        result = await _dispatch(
            service,
            SET_GOAL_PLAN_TOOL,
            {"goal_name": "vacaciones", "amount": 500000, "scope": "solo_mes", "month": "2026-12"},
        )

        assert service.set_calls == [(UUID_LIKE, D("500000"), date(2026, 12, 1), GoalPlanScope.SOLO_MES)]
        assert result.startswith("✅ Plan de Vacaciones playa: $500000 (solo diciembre 2026)")
        assert UUID_LIKE not in result

    async def test_desde_mes_defaults_to_the_current_month(self) -> None:
        service = _service()

        result = await _dispatch(
            service, SET_GOAL_PLAN_TOOL, {"goal_name": "vacaciones", "amount": 300000, "scope": "desde_mes"}
        )

        assert service.set_calls == [(UUID_LIKE, D("300000"), date(2026, 11, 1), GoalPlanScope.DESDE_MES)]
        assert "desde noviembre 2026 en adelante" in result

    async def test_este_mes_is_the_current_month(self) -> None:
        service = _service()

        await _dispatch(
            service,
            SET_GOAL_PLAN_TOOL,
            {"goal_name": "vacaciones", "amount": 1, "scope": "solo_mes", "month": "este_mes"},
        )

        assert service.set_calls[0][2] == date(2026, 11, 1)

    async def test_plan_above_what_is_missing_is_accepted_with_a_heads_up(self) -> None:
        # The goal holds 25.000 of 100.000: 75.000 are missing.
        service = _service()

        result = await _dispatch(
            service,
            SET_GOAL_PLAN_TOOL,
            {"goal_name": "vacaciones", "amount": 200000, "scope": "solo_mes"},
        )

        assert service.set_calls  # accepted
        assert "con $75000 ya la completas" in result

    async def test_plan_for_a_paused_goal_warns_it_does_not_count(self) -> None:
        service = _service(goals=[_goal(id=UUID_LIKE, name="Vacaciones playa", status=GoalStatus.PAUSED)])

        result = await _dispatch(
            service, SET_GOAL_PLAN_TOOL, {"goal_name": "vacaciones", "amount": 10, "scope": "solo_mes"}
        )

        assert "pausada" in result

    async def test_past_month_without_confirmation_asks_and_does_not_write(self) -> None:
        service = _service()

        result = await _dispatch(
            service,
            SET_GOAL_PLAN_TOOL,
            {"goal_name": "vacaciones", "amount": 400000, "scope": "solo_mes", "month": "2026-09"},
        )

        assert service.set_calls == []
        assert result.startswith("¿Confirmas que quieres poner el plan de septiembre 2026 que ya pasó?")
        assert is_write_refused(SET_GOAL_PLAN_TOOL, result)

    @pytest.mark.parametrize("confirm", [True, "true"])
    async def test_past_month_with_confirmation_writes(self, confirm: object) -> None:
        service = _service()

        result = await _dispatch(
            service,
            SET_GOAL_PLAN_TOOL,
            {
                "goal_name": "vacaciones",
                "amount": 400000,
                "scope": "solo_mes",
                "month": "2026-09",
                "confirm_past": confirm,
            },
        )

        assert service.set_calls == [(UUID_LIKE, D("400000"), date(2026, 9, 1), GoalPlanScope.SOLO_MES)]
        assert result.startswith("✅")

    async def test_confirm_false_does_not_confirm(self) -> None:
        service = _service()

        result = await _dispatch(
            service,
            SET_GOAL_PLAN_TOOL,
            {"goal_name": "vacaciones", "amount": 1, "scope": "solo_mes", "month": "2026-09", "confirm_past": False},
        )

        assert service.set_calls == []
        assert result.startswith("¿")

    @pytest.mark.parametrize("amount", [0, -5])
    async def test_non_positive_amount_is_refused(self, amount: int) -> None:
        service = _service()

        result = await _dispatch(
            service, SET_GOAL_PLAN_TOOL, {"goal_name": "vacaciones", "amount": amount, "scope": "solo_mes"}
        )

        assert service.set_calls == []
        assert result.startswith("No ")
        assert "clear_goal_plan" in result

    async def test_unreadable_amount_is_refused(self) -> None:
        result = await _dispatch(
            _service(), SET_GOAL_PLAN_TOOL, {"goal_name": "vacaciones", "amount": "mucho", "scope": "solo_mes"}
        )

        assert result.startswith("No pude")

    @pytest.mark.parametrize("month", ["2026-13", "noviembre", "26-11", "2026-1"])
    async def test_invalid_month_is_refused(self, month: str) -> None:
        service = _service()

        result = await _dispatch(
            service,
            SET_GOAL_PLAN_TOOL,
            {"goal_name": "vacaciones", "amount": 10, "scope": "solo_mes", "month": month},
        )

        assert service.set_calls == []
        assert result.startswith("No entendí el mes")

    async def test_missing_scope_asks_instead_of_guessing(self) -> None:
        service = _service()

        result = await _dispatch(service, SET_GOAL_PLAN_TOOL, {"goal_name": "vacaciones", "amount": 10})

        assert service.set_calls == []
        assert result.startswith("¿")

    async def test_unknown_goal(self) -> None:
        service = _service()

        result = await _dispatch(
            service, SET_GOAL_PLAN_TOOL, {"goal_name": "moto", "amount": 10, "scope": "solo_mes"}
        )

        assert result.startswith("No encontré una meta llamada 'moto'")
        assert service.set_calls == []

    async def test_ambiguous_goal_asks_for_the_target_and_hides_ids(self) -> None:
        goals = [
            _goal(id="a", name="Fondo", target_amount=D("100000")),
            _goal(id="b", name="Fondo", target_amount=D("200000")),
        ]
        service = _service(goals=goals)

        result = await _dispatch(
            service, SET_GOAL_PLAN_TOOL, {"goal_name": "fondo", "amount": 10, "scope": "solo_mes"}
        )

        assert service.set_calls == []
        assert "¿Cuál quieres planear?" in result

    async def test_target_amount_disambiguates(self) -> None:
        goals = [
            _goal(id="a", name="Fondo", target_amount=D("100000")),
            _goal(id="b", name="Fondo", target_amount=D("200000")),
        ]
        service = _service(goals=goals)

        await _dispatch(
            service,
            SET_GOAL_PLAN_TOOL,
            {"goal_name": "fondo", "amount": 10, "scope": "solo_mes", "goal_target_amount": 200000},
        )

        assert service.set_calls[0][0] == "b"

    async def test_domain_errors_come_back_as_plain_spanish(self) -> None:
        error = InvalidPlanPeriodError("2025-01 es anterior a la fecha en que se creó la meta")
        service = _service(plan_error=error)

        result = await _dispatch(
            service,
            SET_GOAL_PLAN_TOOL,
            {"goal_name": "vacaciones", "amount": 10, "scope": "solo_mes", "month": "2026-11"},
        )

        assert result.startswith("No pude guardar el plan: 2025-01 es anterior")
        assert "INVALID_PLAN_PERIOD" not in result and "Traceback" not in result
        assert UUID_LIKE not in result


class TestClearGoalPlan:
    @pytest.mark.parametrize(
        ("mode", "expected_text"),
        [
            ("sin_plan", "Quité el plan de Vacaciones playa para diciembre 2026"),
            ("volver_al_general", "en diciembre 2026 vuelve al plan normal"),
            ("terminar", "Dejé de planear Vacaciones playa desde diciembre 2026"),
        ],
    )
    async def test_modes(self, mode: str, expected_text: str) -> None:
        service = _service(resolved=D("500000"))

        result = await _dispatch(
            service,
            CLEAR_GOAL_PLAN_TOOL,
            {"goal_name": "vacaciones", "mode": mode, "month": "2026-12"},
        )

        assert service.clear_calls == [(UUID_LIKE, date(2026, 12, 1), GoalPlanClearMode(mode))]
        assert result.startswith("✅") and expected_text in result
        assert UUID_LIKE not in result

    async def test_volver_al_general_reports_the_general_plan(self) -> None:
        result = await _dispatch(
            _service(resolved=D("500000")),
            CLEAR_GOAL_PLAN_TOOL,
            {"goal_name": "vacaciones", "mode": "volver_al_general", "month": "2026-12"},
        )

        assert "($500000 al mes)" in result

    async def test_default_month_is_the_current_one(self) -> None:
        service = _service()

        await _dispatch(service, CLEAR_GOAL_PLAN_TOOL, {"goal_name": "vacaciones", "mode": "terminar"})

        assert service.clear_calls[0][1] == date(2026, 11, 1)

    async def test_past_month_asks_first_and_then_writes_when_confirmed(self) -> None:
        service = _service()
        args: dict[str, object] = {"goal_name": "vacaciones", "mode": "sin_plan", "month": "2026-08"}

        asked = await _dispatch(service, CLEAR_GOAL_PLAN_TOOL, args)
        assert asked.startswith("¿Confirmas") and service.clear_calls == []

        done = await _dispatch(service, CLEAR_GOAL_PLAN_TOOL, {**args, "confirm_past": True})
        assert done.startswith("✅") and len(service.clear_calls) == 1

    async def test_missing_mode_asks(self) -> None:
        service = _service()

        result = await _dispatch(service, CLEAR_GOAL_PLAN_TOOL, {"goal_name": "vacaciones"})

        assert result.startswith("¿") and service.clear_calls == []

    async def test_invalid_month_unknown_goal_and_ambiguity(self) -> None:
        service = _service()
        bad_month = await _dispatch(
            service, CLEAR_GOAL_PLAN_TOOL, {"goal_name": "vacaciones", "mode": "sin_plan", "month": "x"}
        )
        unknown = await _dispatch(service, CLEAR_GOAL_PLAN_TOOL, {"goal_name": "moto", "mode": "sin_plan"})
        ambiguous = await _dispatch(
            _service(goals=[_goal(id="a", name="Fondo"), _goal(id="b", name="Fondo", target_amount=D("5"))]),
            CLEAR_GOAL_PLAN_TOOL,
            {"goal_name": "fondo", "mode": "sin_plan"},
        )

        assert bad_month.startswith("No entendí el mes")
        assert unknown.startswith("No encontré")
        assert "¿Cuál quieres" in ambiguous
        assert service.clear_calls == []


class TestCreateGoalWithPlan:
    async def test_monthly_plan_is_saved_as_a_recurring_from_this_month(self) -> None:
        service = _service()

        result = await _dispatch(
            service, "create_goal", {"name": "Moto", "target_amount": 8000000, "monthly_plan": 400000}
        )

        assert service.set_calls[0][1:] == (
            D("400000"),
            date(2026, 11, 1),
            GoalPlanScope.DESDE_MES,
        )
        assert "Meta creada" in result
        assert "Plan: $400000 al mes desde noviembre 2026" in result

    async def test_plan_never_starts_before_the_goals_creation_month(self) -> None:
        # Created Dec 1st 00:00 in Bogota while "today" is still in November.
        service = _service()
        service.created_at = datetime(2026, 12, 1, 5, 0, tzinfo=UTC)

        await _dispatch(
            service, "create_goal", {"name": "Moto", "target_amount": 1000, "monthly_plan": 10}
        )

        assert service.set_calls[0][2] == date(2026, 12, 1)

    async def test_invalid_plan_creates_nothing(self) -> None:
        service = _service()

        result = await _dispatch(
            service, "create_goal", {"name": "Moto", "target_amount": 1000, "monthly_plan": 0}
        )

        assert result.startswith("No pude crear la meta")
        assert service.created == []

    async def test_without_plan_nothing_is_planned(self) -> None:
        service = _service()

        await _dispatch(service, "create_goal", {"name": "Moto", "target_amount": 1000})

        assert service.set_calls == []

    async def test_plan_failure_still_reports_the_created_goal(self) -> None:
        service = _service(plan_error=InvalidPlanPeriodError("algo falló"))

        result = await _dispatch(
            service, "create_goal", {"name": "Moto", "target_amount": 1000, "monthly_plan": 10}
        )

        assert "Meta creada" in result and "No pude guardar el plan mensual" in result


class TestQueryGoalsPlanLines:
    async def test_goal_with_plan_shows_plan_contributed_and_missing(self) -> None:
        service = _service(statuses=[_status(UUID_LIKE, planned="500000", saved="200000", percentage=40.0)])

        result = await _dispatch(service, "query_goals", {})

        assert "Vacaciones playa" in result and "25%" in result  # existing line intact
        assert "plan $500000 · aportado $200000 (40%) · faltan $300000" in result
        assert UUID_LIKE not in result

    async def test_goal_without_plan_says_so(self) -> None:
        result = await _dispatch(_service(), "query_goals", {})

        assert "· sin plan" in result
        assert "TOTAL PLAN METAS" not in result

    async def test_met_goal_and_withdrawals(self) -> None:
        service = _service(
            statuses=[_status(UUID_LIKE, planned="100", saved="150", withdrawn="30", percentage=100.0)]
        )

        result = await _dispatch(service, "query_goals", {})

        assert "✓ cumplido" in result
        assert "retiraste $30" in result

    async def test_plan_capped_to_what_was_missing_is_explained(self) -> None:
        service = _service(
            statuses=[_status(UUID_LIKE, planned="2000", saved="0", effective="500", remaining="500")]
        )

        result = await _dispatch(service, "query_goals", {})

        assert "solo te faltaban $500" in result
        assert "faltan $500" in result

    async def test_suggested_monthly_when_there_is_no_plan(self) -> None:
        service = _service(suggested=D("6363.64"))

        result = await _dispatch(service, "query_goals", {})

        assert "sin plan · sugerido $6363.64/mes (no guardado)" in result

    async def test_suggestion_is_not_shown_when_a_plan_exists(self) -> None:
        service = _service(statuses=[_status(UUID_LIKE)], suggested=D("6363.64"))

        assert "sugerido" not in await _dispatch(service, "query_goals", {})

    async def test_paused_goal_is_not_asked_for_a_plan(self) -> None:
        service = _service(goals=[_goal(id=UUID_LIKE, name="Viaje", status=GoalStatus.PAUSED)])

        assert "pausada" in await _dispatch(service, "query_goals", {})

    async def test_totals_are_summed_in_code_and_grouped_by_currency(self) -> None:
        goals = [
            _goal(id="a", name="Uno"),
            _goal(id="b", name="Dos"),
            _goal(id="c", name="Tres", currency=CurrencyType.USD),
        ]
        service = _service(
            goals=goals,
            statuses=[
                _status("a", planned="100.10", saved="40.05"),
                _status("b", planned="200.20", saved="60.10"),
                _status("c", planned="50", saved="10", currency=CurrencyType.USD),
            ],
        )

        result = await _dispatch(service, "query_goals", {})

        assert "TOTAL PLAN METAS (el plan no es gasto; lo aportado sí cuenta en tus gastos del mes) [MXN]: planificado $300.30 · aportado $100.15" in result
        assert "TOTAL PLAN METAS (el plan no es gasto; lo aportado sí cuenta en tus gastos del mes) [USD]: planificado $50 · aportado $10" in result

    async def test_single_currency_total_has_no_currency_tag(self) -> None:
        service = _service(statuses=[_status(UUID_LIKE, planned="500", saved="200")])

        result = await _dispatch(service, "query_goals", {})

        assert result.splitlines()[-1] == (
            "TOTAL PLAN METAS (el plan no es gasto; lo aportado sí cuenta en tus gastos del mes): planificado $500 · aportado $200"
        )

    async def test_period_selects_the_month(self) -> None:
        service = _service()

        await _dispatch(service, "query_goals", {"period": "2026-08"})
        await _dispatch(service, "query_goals", {"period": "mes_pasado"})
        await _dispatch(service, "query_goals", {})

        assert service.status_calls == [
            (date(2026, 8, 1), date(2026, 8, 31)),
            (date(2026, 10, 1), date(2026, 10, 31)),
            (date(2026, 11, 1), date(2026, 11, 30)),
        ]

    async def test_invalid_period_is_refused(self) -> None:
        result = await _dispatch(_service(), "query_goals", {"period": "ayer"})

        assert result.startswith("No entendí el período")

    async def test_single_goal_shows_its_plan_line(self) -> None:
        service = _service(statuses=[_status(UUID_LIKE)])

        result = await _dispatch(service, "query_goals", {"goal_name": "vacaciones"})

        assert "plan $500000" in result

    async def test_month_by_month_for_one_goal(self) -> None:
        def line(month: int, planned: str | None, saved: str, withdrawn: str = "0") -> GoalMonthLine:
            return GoalMonthLine(
                goal_id=UUID_LIKE,
                goal_name="Vacaciones playa",
                currency=CurrencyType.MXN,
                month=date(2026, month, 1),
                planned=D(planned) if planned is not None else None,
                saved=D(saved),
                withdrawn=D(withdrawn),
                cumulative=D("1000"),
            )

        other = line(10, "1", "1").model_copy(update={"goal_id": "other"})
        service = _service(
            history=[line(9, None, "0"), line(10, "500", "300", "50"), line(11, "500", "0"), other]
        )

        result = await _dispatch(service, "query_goals", {"goal_name": "vacaciones", "months": 6})

        assert service.history_calls == [(6, date(2026, 11, 1))]
        assert "septiembre 2026: sin plan · aportado $0 · acumulado $1000" in result
        assert "octubre 2026: plan $500 · aportado $300 · retiraste $50 · acumulado $1000" in result
        assert "noviembre 2026: plan $500 · aportado $0" in result
        assert result.count("2026:") == 3  # the other goal's line is not shown

    async def test_months_without_a_goal_name_is_ignored(self) -> None:
        service = _service()

        await _dispatch(service, "query_goals", {"months": 6})

        assert service.history_calls == []


def _turn(turn_id: str) -> TurnContext:
    return TurnContext(turn_id=turn_id, conversation_id="c1")


class TestConfirmPastCannotBeSelfGranted:
    ARGS: dict[str, object] = {
        "goal_name": "vacaciones",
        "amount": 400000,
        "scope": "solo_mes",
        "month": "2026-08",
    }

    async def test_confirm_past_in_the_same_turn_as_the_question_is_refused(self) -> None:
        service = _service()

        with bound_turn(_turn("t1")):
            asked = await _dispatch(service, SET_GOAL_PLAN_TOOL, self.ARGS)
            forced = await _dispatch(service, SET_GOAL_PLAN_TOOL, {**self.ARGS, "confirm_past": True})

        assert asked.startswith("¿Confirmas")
        assert forced.startswith("No ")
        assert "siguiente mensaje" in forced
        assert service.set_calls == []
        assert is_write_refused(SET_GOAL_PLAN_TOOL, forced)

    async def test_in_a_new_turn_the_confirmation_writes(self) -> None:
        service = _service()
        with bound_turn(_turn("t1")):
            await _dispatch(service, SET_GOAL_PLAN_TOOL, self.ARGS)

        with bound_turn(_turn("t2")):
            done = await _dispatch(service, SET_GOAL_PLAN_TOOL, {**self.ARGS, "confirm_past": True})

        assert done.startswith("✅")
        assert len(service.set_calls) == 1

    async def test_a_question_does_not_leak_into_the_next_turn_context(self) -> None:
        service = _service()
        with bound_turn(_turn("t1")):
            await _dispatch(service, SET_GOAL_PLAN_TOOL, self.ARGS)
        # Same goal and month, fresh turn, no question asked in it: allowed.
        with bound_turn(_turn("t2")):
            result = await _dispatch(service, SET_GOAL_PLAN_TOOL, {**self.ARGS, "confirm_past": True})

        assert result.startswith("✅")

    async def test_a_different_month_asked_in_the_turn_does_not_block_another(self) -> None:
        service = _service()

        with bound_turn(_turn("t1")):
            await _dispatch(service, SET_GOAL_PLAN_TOOL, self.ARGS)
            other = await _dispatch(
                service, SET_GOAL_PLAN_TOOL, {**self.ARGS, "month": "2026-09", "confirm_past": True}
            )

        assert other.startswith("✅")

    async def test_clear_plan_has_the_same_guard(self) -> None:
        service = _service()
        args: dict[str, object] = {"goal_name": "vacaciones", "mode": "sin_plan", "month": "2026-08"}

        with bound_turn(_turn("t1")):
            asked = await _dispatch(service, CLEAR_GOAL_PLAN_TOOL, args)
            forced = await _dispatch(service, CLEAR_GOAL_PLAN_TOOL, {**args, "confirm_past": True})

        assert asked.startswith("¿") and forced.startswith("No ")
        assert service.clear_calls == []


class TestPlanTotalsUseTheEffectivePlan:
    async def test_total_shows_planned_and_what_was_really_needed(self) -> None:
        service = _service(
            statuses=[_status(UUID_LIKE, planned="2000", saved="0", effective="500", remaining="500")]
        )

        result = await _dispatch(service, "query_goals", {})

        assert result.splitlines()[-1] == (
            "TOTAL PLAN METAS (el plan no es gasto; lo aportado sí cuenta en tus gastos del mes): planificado $2000 (necesitabas $500) · aportado $0"
        )

    async def test_total_stays_plain_when_no_plan_was_capped(self) -> None:
        service = _service(statuses=[_status(UUID_LIKE, planned="500", saved="200")])

        result = await _dispatch(service, "query_goals", {})

        assert "necesitabas" not in result


class TestQueryGoalsListsEveryGoal:
    async def test_goals_beyond_the_first_page_are_listed_and_counted(self) -> None:
        goals = [_goal(id=f"g{i}", name=f"Meta {i:02d}") for i in range(45)]
        statuses = [_status(f"g{i}", planned="10", saved="0") for i in range(45)]
        service = _service(goals=goals, statuses=statuses)

        result = await _dispatch(service, "query_goals", {})

        assert result.startswith("45 meta(s):")
        assert result.count("- Meta ") == 45
        assert result.splitlines()[-1].endswith("planificado $450 · aportado $0")


class TestSpendingTexts:
    async def test_saving_a_plan_says_it_is_only_a_plan(self) -> None:
        result = await _dispatch(
            _service(), SET_GOAL_PLAN_TOOL, {"goal_name": "vacaciones", "amount": 500000, "scope": "solo_mes"}
        )

        assert (
            'Quedó como plan (no es un tope ni un gasto, y aún no has aportado). Cuando muevas la '
            'plata, dime "aporté $X a Vacaciones playa" y lo registro; ahí sí contará en tus gastos del mes.'
        ) in result

    async def test_a_contribution_says_it_counts_in_the_months_spending(self) -> None:
        result = await _dispatch(
            _service(), "contribute_to_goal", {"goal_name": "vacaciones", "amount": 500000}
        )

        assert "(cuenta en tus gastos del mes como ahorro)" in result

    async def test_plan_totals_label_explains_the_difference(self) -> None:
        service = _service(statuses=[_status(UUID_LIKE, planned="500", saved="200")])

        result = await _dispatch(service, "query_goals", {})

        assert "(el plan no es gasto; lo aportado sí cuenta en tus gastos del mes)" in result
        assert "no es gasto ni tope" not in result


class TestContributionSpendingNote:
    async def test_a_contribution_before_the_cutoff_does_not_claim_to_count(self) -> None:
        result = await _dispatch(
            _service(),
            "contribute_to_goal",
            {"goal_name": "vacaciones", "amount": 500000, "date": "2026-07-15"},
        )

        assert "cuenta en tus gastos del mes como ahorro" not in result
        assert "no cuenta en tus gastos" in result

    async def test_a_contribution_from_the_cutoff_on_says_it_counts(self) -> None:
        result = await _dispatch(
            _service(),
            "contribute_to_goal",
            {"goal_name": "vacaciones", "amount": 500000, "date": "2026-11-01"},
        )

        assert "(cuenta en tus gastos del mes como ahorro)" in result


class TestCreateGoalCurrency:
    async def test_the_chat_leaves_the_currency_to_the_service_default(self) -> None:
        service = _service()

        await _dispatch(service, "create_goal", {"name": "Moto", "target_amount": 1000})

        assert service.created[0][0].currency is None
