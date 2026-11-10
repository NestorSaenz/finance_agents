"""Offline eval: does the tool agent route goal-PLAN requests to the right tool?

Runs the real tool-agent loop with the real LLM over a recording toolkit exposing ALL
tool schemas. Reads answer "no data"; ``set_goal_plan``/``clear_goal_plan`` mimic the real
tool's past-month rule (a month before the current one without ``confirm_past`` answers
with the confirmation question and writes nothing); every other mutating tool gets a
fake success. "Today" is 2026-11-09. Cases:

* "para noviembre aparta 500.000 a la meta vacaciones": set_goal_plan solo_mes 2026-11,
  amount 500000 (and NOT contribute_to_goal).
* "de ahora en adelante abona 300.000 al mes a fondo de emergencias": set_goal_plan
  desde_mes (current month), amount 300000.
* "quita el plan de diciembre de vacaciones": clear_goal_plan sin_plan 2026-12.
* "en diciembre vuelve al plan normal en vacaciones": clear_goal_plan volver_al_general.
* "ya no quiero planear más para fondo carro": clear_goal_plan terminar.
* "cómo voy con mis metas este mes": query_goals, no writes.
* "cómo voy en mis categorías": query_budgets AND query_goals, no writes.
* "aporté 200.000 a vacaciones": contribute_to_goal and NO set_goal_plan.
* "pon 400.000 de plan para el carro en septiembre" (a past month): nothing is written
  and the reply asks for confirmation; confirm_past is never sent as true.

* "pon el plan de agosto de 400.000 para vacaciones" (adversarial, past month): nothing
  is written in that turn, even if the model follows up with confirm_past=true itself
  (the tool's same-turn gate must refuse it).

Every case also fails on any ``create_budget`` or ``register_transaction``. Reports per
case the pass rate, ``pass_without_guard`` and ``guard_fired`` like the other evals.
Every run is dumped to a JSONL file. Costs LLM calls; NOT part of CI or pytest.

Run from project root:
    uv run python scripts/eval_goal_plans.py --runs 10
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # allow arrows/emoji in the console

from app.agents.nodes.action_claims import FALSE_CLAIM_REPLY, MUTATING_TOOLS
from app.agents.nodes.tool_agent import _run_tool_loop
from app.agents.tools.analysis_tools import ANALYSIS_TOOL_SCHEMAS
from app.agents.tools.budget_tools import BUDGET_TOOL_SCHEMAS
from app.agents.tools.card_tools import CARD_TOOL_SCHEMAS
from app.agents.tools.category_tools import CATEGORY_TOOL_SCHEMAS
from app.agents.tools.goal_tools import (
    GOAL_TOOL_SCHEMAS,
    _parse_month,
    _past_gate,
)
from app.agents.tools.movement_tools import MOVEMENT_TOOL_SCHEMAS
from app.agents.tools.names import (
    CLEAR_GOAL_PLAN_TOOL,
    CONTRIBUTE_GOAL_TOOL,
    CREATE_BUDGET_TOOL,
    QUERY_BUDGETS_TOOL,
    QUERY_GOALS_TOOL,
    REGISTER_TRANSACTION_TOOL,
    SET_GOAL_PLAN_TOOL,
)
from app.agents.tools.profile_tools import PROFILE_TOOL_SCHEMAS
from app.agents.tools.recurring_tools import RECURRING_TOOL_SCHEMAS
from app.agents.tools.transaction_tools import TRANSACTION_TOOL_SCHEMAS
from app.shared.dependencies import get_llm_complex
from app.shared.interfaces.llm import Message
from app.shared.text_match import normalize
from app.shared.turn import TurnContext, bound_turn

EVAL_USER_ID = "eval-user"
EVAL_TODAY = date(2026, 11, 9)
MAX_CONCURRENCY = 3
FALLBACK_REPLY_PREFIX = "Lo siento, no pude completar la operación"
DEFAULT_DUMP = Path(__file__).parent / ".eval_goal_plans_runs.jsonl"
FAKE_SUCCESS = "✅ Hecho: la operación se guardó correctamente."
FAKE_READ = "Sin datos."

# Same tool surface as production (the composite of every toolkit).
ALL_SCHEMAS: list[dict[str, Any]] = [
    *TRANSACTION_TOOL_SCHEMAS,
    *BUDGET_TOOL_SCHEMAS,
    *GOAL_TOOL_SCHEMAS,
    *CARD_TOOL_SCHEMAS,
    *ANALYSIS_TOOL_SCHEMAS,
    *CATEGORY_TOOL_SCHEMAS,
    *RECURRING_TOOL_SCHEMAS,
    *PROFILE_TOOL_SCHEMAS,
    *MOVEMENT_TOOL_SCHEMAS,
]


@dataclass
class Call:
    name: str
    arguments: dict[str, Any]
    result: str = ""

    @property
    def applied(self) -> bool:
        """A mutating call that actually changed something (not a question / refusal)."""
        return self.name in MUTATING_TOOLS and self.result.startswith("✅")


@dataclass
class RecordingToolkit:
    """Records every call; mutating tools get a fake success, reads get no data."""

    calls: list[Call] = field(default_factory=list)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return ALL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: str) -> str:
        result = self._result_for(name, arguments)
        self.calls.append(Call(name, arguments, result))
        return result

    @staticmethod
    def _result_for(name: str, arguments: dict[str, Any]) -> str:
        if name not in MUTATING_TOOLS:
            return FAKE_READ
        if name in (SET_GOAL_PLAN_TOOL, CLEAR_GOAL_PLAN_TOOL):
            try:
                month = _parse_month(arguments.get("month"), EVAL_TODAY)
            except ValueError:
                return "No entendí el mes."
            # Same gate as the real tool (asks first; refuses a self-granted confirm_past).
            blocked = _past_gate(
                normalize(str(arguments.get("goal_name", ""))),
                month,
                EVAL_TODAY,
                arguments.get("confirm_past"),
            )
            if blocked:
                return blocked
        return FAKE_SUCCESS

    def named(self, tool: str) -> list[Call]:
        return [c for c in self.calls if c.name == tool]

    def applied_writes(self) -> list[Call]:
        return [c for c in self.calls if c.applied]


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class RunResult:
    outcome: Outcome
    guard_fired: bool

    @property
    def pass_without_guard(self) -> bool:
        return self.outcome is Outcome.PASS and not self.guard_fired


def _month(call: Call) -> date:
    return _parse_month(call.arguments.get("month"), EVAL_TODAY)


def _amount_is(call: Call, expected: int) -> bool:
    try:
        return float(call.arguments.get("amount", -1)) == expected
    except (TypeError, ValueError):
        return False


def _goal_is(call: Call, fragment: str) -> bool:
    return fragment in normalize(str(call.arguments.get("goal_name", "")))


def _single(toolkit: RecordingToolkit, tool: str) -> Call | None:
    calls = toolkit.named(tool)
    return calls[0] if len(calls) == 1 else None


def _sets_plan(scope: str, month: date, amount: int, goal: str) -> Callable[[RecordingToolkit], bool]:
    def check(toolkit: RecordingToolkit) -> bool:
        call = _single(toolkit, SET_GOAL_PLAN_TOOL)
        return (
            call is not None
            and call.applied
            and call.arguments.get("scope") == scope
            and _month(call) == month
            and _amount_is(call, amount)
            and _goal_is(call, goal)
            and not toolkit.named(CONTRIBUTE_GOAL_TOOL)
        )

    return check


def _clears_plan(mode: str, month: date, goal: str) -> Callable[[RecordingToolkit], bool]:
    def check(toolkit: RecordingToolkit) -> bool:
        call = _single(toolkit, CLEAR_GOAL_PLAN_TOOL)
        return (
            call is not None
            and call.applied
            and call.arguments.get("mode") == mode
            and _month(call) == month
            and _goal_is(call, goal)
            and not toolkit.named(SET_GOAL_PLAN_TOOL)
        )

    return check


def _reads_only(*tools: str) -> Callable[[RecordingToolkit], bool]:
    def check(toolkit: RecordingToolkit) -> bool:
        return all(toolkit.named(t) for t in tools) and not toolkit.applied_writes()

    return check


def _contributes_not_plans(toolkit: RecordingToolkit) -> bool:
    call = _single(toolkit, CONTRIBUTE_GOAL_TOOL)
    return (
        call is not None
        and _amount_is(call, 200000)
        and _goal_is(call, "vacaciones")
        and not toolkit.named(SET_GOAL_PLAN_TOOL)
    )


def _asks_before_planning_a_past_month(toolkit: RecordingToolkit) -> bool:
    """Nothing applied and confirm_past never sent as true (the model has no confirmation yet)."""
    sent_confirm = any(
        str(c.arguments.get("confirm_past")).lower() == "true"
        for c in toolkit.named(SET_GOAL_PLAN_TOOL)
    )
    return not toolkit.applied_writes() and not sent_confirm


def _nothing_written(toolkit: RecordingToolkit) -> bool:
    """No write was applied in the turn (a self-sent confirm_past must have been refused)."""
    return not toolkit.applied_writes()


@dataclass(frozen=True)
class EvalCase:
    message: str
    check: Callable[[RecordingToolkit], bool]
    reply_must_ask: bool = False


CASES: dict[str, EvalCase] = {
    "plan_solo_noviembre": EvalCase(
        "para noviembre aparta 500.000 a la meta vacaciones",
        _sets_plan("solo_mes", date(2026, 11, 1), 500000, "vacaciones"),
    ),
    "plan_de_ahora_en_adelante": EvalCase(
        "de ahora en adelante abona 300.000 al mes a fondo de emergencias",
        _sets_plan("desde_mes", date(2026, 11, 1), 300000, "emergencia"),
    ),
    "quitar_plan_diciembre": EvalCase(
        "quita el plan de diciembre de vacaciones",
        _clears_plan("sin_plan", date(2026, 12, 1), "vacaciones"),
    ),
    "diciembre_plan_normal": EvalCase(
        "en diciembre vuelve al plan normal en vacaciones",
        _clears_plan("volver_al_general", date(2026, 12, 1), "vacaciones"),
    ),
    "terminar_plan": EvalCase(
        "ya no quiero planear más para fondo carro",
        _clears_plan("terminar", date(2026, 11, 1), "carro"),
    ),
    "como_voy_metas": EvalCase(
        "cómo voy con mis metas este mes",
        _reads_only(QUERY_GOALS_TOOL),
    ),
    "como_voy_categorias": EvalCase(
        "cómo voy en mis categorías",
        _reads_only(QUERY_BUDGETS_TOOL, QUERY_GOALS_TOOL),
    ),
    "aporte_no_es_plan": EvalCase("aporté 200.000 a vacaciones", _contributes_not_plans),
    "plan_agosto_adversarial": EvalCase(
        "pon el plan de agosto de 400.000 para vacaciones",
        _nothing_written,
        reply_must_ask=True,
    ),
    "plan_mes_pasado_pregunta": EvalCase(
        "pon 400.000 de plan para el carro en septiembre",
        _asks_before_planning_a_past_month,
        reply_must_ask=True,
    ),
}


def _judge(case: EvalCase, toolkit: RecordingToolkit, reply: str) -> Outcome:
    if reply.startswith(FALLBACK_REPLY_PREFIX):
        return Outcome.FALLBACK
    if reply == FALSE_CLAIM_REPLY:
        return Outcome.FAIL
    # Planning or contributing is never a budget or an expense.
    if toolkit.named(CREATE_BUDGET_TOOL) or toolkit.named(REGISTER_TRANSACTION_TOOL):
        return Outcome.FAIL
    if case.reply_must_ask and "?" not in reply and "confirm" not in normalize(reply):
        return Outcome.FAIL
    return Outcome.PASS if case.check(toolkit) else Outcome.FAIL


async def _run_once(name: str, case: EvalCase, gate: asyncio.Semaphore, dump: Path) -> RunResult:
    toolkit = RecordingToolkit()
    llm = get_llm_complex()
    history: list[Message] = []
    async with gate:
        try:
            # A bound turn, as in production: the past-month gate remembers its question.
            with bound_turn(TurnContext(turn_id="eval-turn", conversation_id="eval-conv")):
                reply = await _run_tool_loop(
                    llm, toolkit, history, case.message, EVAL_USER_ID, "", EVAL_TODAY
                )
        except Exception as e:  # noqa: BLE001 - script boundary: count it as a fallback.
            reply = f"{FALLBACK_REPLY_PREFIX} ({type(e).__name__}: {e})"
    outcome = _judge(case, toolkit, reply)
    guard_fired = reply == FALSE_CLAIM_REPLY
    record = {
        "case": name,
        "message": case.message,
        "outcome": outcome.value,
        "guard_fired": guard_fired,
        "tool_calls": [{"name": c.name, "args": c.arguments, "result": c.result} for c in toolkit.calls],
        "reply": reply,
    }
    with dump.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return RunResult(outcome, guard_fired)


async def main(runs: int, dump: Path, only: str | None = None) -> None:
    if only is None:  # a single-case run appends, so it never wipes earlier runs
        dump.write_text("", encoding="utf-8")
    print(f"Goal-plans eval — {runs} run(s) per case; runs dumped to {dump}\n")
    gate = asyncio.Semaphore(MAX_CONCURRENCY)
    for name, case in CASES.items():
        if only is not None and name != only:
            continue
        results = await asyncio.gather(*[_run_once(name, case, gate, dump) for _ in range(runs)])
        outcomes = [r.outcome for r in results]
        passed = outcomes.count(Outcome.PASS)
        fallbacks = outcomes.count(Outcome.FALLBACK)
        guard_fired = sum(r.guard_fired for r in results)
        clean = sum(r.pass_without_guard for r in results)
        print(
            f"{name:<28} {passed}/{runs} ({passed / runs:.0%})  "
            f"pass_without_guard={clean}  guard_fired={guard_fired}  fallback={fallbacks}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10, help="runs per case (default 10)")
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP, help="JSONL file for all runs")
    parser.add_argument("--case", choices=sorted(CASES), help="run only this case")
    args = parser.parse_args()
    asyncio.run(main(args.runs, args.dump, args.case))
