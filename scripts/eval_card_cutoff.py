"""Offline eval: does Safi change a card's cutoff day ONLY after the user's confirmation?

Runs the real tool-agent loop with the real LLM and the REAL ``CardToolkit`` +
``CardScheduleChangeService`` over an in-memory card service (one card "Rappi", corte
19, pago 2, a realistic balance) and an in-memory pending store with the production
RPC semantics, so ``query_cards`` / ``update_card`` / ``confirm_card_change`` produce
production-shaped text. Every other tool is stubbed; mutating calls are recorded and
count as failures. A bound ``TurnContext`` per phase (new ``turn_id`` each) mirrors the
chat route.

Requests (``periodo``, ``ciclo`` ...): turn 1 must yield a PROPOSAL with an accepted
cutoff and leave the card unchanged; turn 2 (history + "sí", new turn) must call
``confirm_card_change`` and leave the card at the accepted cutoff.
Statements ("Pero el corte fue el 20 de septiembre"): the card must stay unchanged
after turn 1 and the reply must contain a proposal or a question.
Also reports, per case, same-turn ``confirm_card_change`` attempts (the code makes them
no-ops; the metric shows how often the model tries). Every run is dumped to a JSONL file.
Costs LLM calls; NOT part of CI or pytest.

Run from project root:
    uv run python scripts/eval_card_cutoff.py --runs 10
"""

import argparse
import asyncio
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # allow arrows in the console

from app.agents.nodes.tool_agent import _run_tool_loop
from app.agents.tools.analysis_tools import ANALYSIS_TOOL_SCHEMAS
from app.agents.tools.budget_tools import BUDGET_TOOL_SCHEMAS
from app.agents.tools.card_tools import (
    CARD_TOOL_SCHEMAS,
    CONFIRM_CARD_CHANGE_TOOL,
    QUERY_CARDS_TOOL,
    UPDATE_CARD_TOOL,
    CardToolkit,
)
from app.agents.tools.category_tools import CATEGORY_TOOL_SCHEMAS
from app.agents.tools.goal_tools import GOAL_TOOL_SCHEMAS
from app.agents.tools.movement_tools import MOVEMENT_TOOL_SCHEMAS
from app.agents.tools.profile_tools import PROFILE_TOOL_SCHEMAS
from app.agents.tools.recurring_tools import RECURRING_TOOL_SCHEMAS
from app.agents.tools.transaction_tools import TRANSACTION_TOOL_SCHEMAS
from app.shared.dependencies import get_llm_complex
from app.shared.interfaces.llm import Message, MessageRole
from app.shared.turn import TurnContext, bound_turn
from app.shared.types import UserId
from app.src.cards.models import CreditCardStatus
from app.src.cards.services.schedule_change_service import CardScheduleChangeService
from app.src.pending.services.pending_action_service import PendingActionService
from tests.fakes import FakePendingActionRepository
from tests.unit.agents.test_card_tools import FakeCardService, _card

EVAL_USER_ID = "eval-user"
EVAL_CONVERSATION_ID = "eval-conversation"
EVAL_TODAY = date(2026, 10, 1)
MAX_CONCURRENCY = 3
FALLBACK_REPLY_PREFIX = "Lo siento, no pude completar la operación"
CONFIRMATION_MESSAGE = "Sí, cámbialo"
PROPOSAL_PREFIX = "PROPUESTA (aún NO aplicada)"
APPLIED_PREFIX = "✏️ Actualicé"
INITIAL_CUTOFF = 19
DEFAULT_DUMP = Path(__file__).parent / ".eval_card_cutoff_runs.jsonl"
# Tools that only read data; any other tool besides the card-change pair counts as a failure.
ALLOWED_WRITES = frozenset({UPDATE_CARD_TOOL, CONFIRM_CARD_CHANGE_TOOL})
READ_ONLY_PREFIXES = ("query_", "list_", "analyze_", "spending_", "find_")

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


class CaseKind(StrEnum):
    REQUEST = "request"  # the user asks for the change: propose, then confirm next turn
    STATEMENT = "statement"  # the user only states a fact: propose/ask, never change


@dataclass(frozen=True)
class EvalCase:
    message: str
    accepted_cutoffs: frozenset[int]
    proposal: re.Pattern[str]
    kind: CaseKind = CaseKind.REQUEST


QUESTION_ABOUT_20 = r"¿[^?]*(cambi|actualiz)[^?]*\b20\b[^?]*\?"
PROPOSES_20 = re.compile(rf"→\s*20\b|{QUESTION_ABOUT_20}", re.IGNORECASE)
PROPOSES_MONTH_END = re.compile(
    r"→\s*(30|31)\b|fin de mes|último día|¿[^?]*(cambi|actualiz)[^?]*\b(30|31)\b[^?]*\?",
    re.IGNORECASE,
)
# Any refusal/deflection fails the run.
REFUSAL = re.compile(
    r"\bbanco\b[^.]{0,60}(cambi|modific|defin|gestion)"
    r"|no (puedo|es posible)|comun[ií]cate|entidad emisora",
    re.IGNORECASE,
)

CASES: dict[str, EvalCase] = {
    "periodo": EvalCase(
        "Puede modificar el periodo de facturación la tarjeta de rappi del 21 de agosto "
        "al 20 de septiembre?",
        frozenset({20}),
        PROPOSES_20,
    ),
    "ciclo": EvalCase(
        "Cambia el ciclo de mi tarjeta Rappi: va del 21 de agosto al 20 de septiembre",
        frozenset({20}),
        PROPOSES_20,
    ),
    "fecha_corte": EvalCase(
        "La fecha de corte de la Rappi es el 20 de septiembre, actualízala",
        frozenset({20}),
        PROPOSES_20,
    ),
    "solo_inicio": EvalCase(
        "El periodo de facturación de la Rappi empieza desde el 21",
        frozenset({20}),
        PROPOSES_20,
    ),
    "fin_de_mes": EvalCase(
        "El periodo de la Rappi va del 1 al 30 de septiembre, ajústalo",
        frozenset({30, 31}),
        PROPOSES_MONTH_END,
    ),
    "explicito": EvalCase("cambia el corte de Rappi al 20", frozenset({20}), PROPOSES_20),
    "afirmacion": EvalCase(
        "Pero el corte fue el 20 de septiembre",
        frozenset({20}),
        PROPOSES_20,
        CaseKind.STATEMENT,
    ),
    "queja": EvalCase(
        "Creo que el corte de mi Rappi está mal, fue el 20 de septiembre",
        frozenset({20}),
        PROPOSES_20,
        CaseKind.STATEMENT,
    ),
}

# Astrid's real transcript; both Safi answers came from the OLD buggy dates.
ASTRID_HISTORY: list[Message] = [
    Message(MessageRole.USER, "Cuanto tengo q pagar en la tarjeta de rappi el 1 de octubre?"),
    Message(
        MessageRole.ASSISTANT,
        "Astrid, para el 1 de octubre no tienes pagos pendientes en tu tarjeta Rappi. "
        "El próximo pago es el 2 de noviembre por $10.573.212 COP.",
    ),
    Message(
        MessageRole.USER,
        "Como no voy a tener si el corte fue el 20 de septiembre y no he pagado esos "
        "movimientos entre el 20 de agosto y el 20 de septiembre",
    ),
    Message(
        MessageRole.ASSISTANT,
        "Entiendo tu preocupación, Astrid. Sin embargo, la información que tengo es que el "
        "próximo pago de tu tarjeta Rappi es el 2 de noviembre por $10.573.212 COP. No "
        "tengo detalles sobre un corte el 20 de septiembre ni movimientos pendientes entre "
        "el 20 de agosto y el 20 de septiembre.",
    ),
]


class RappiCardService(FakeCardService):
    """In-memory service: Rappi (corte 19, pago 2) as of 2026-10-01."""

    def __init__(self) -> None:
        card = _card("Rappi").model_copy(
            update={
                "cutoff_day": INITIAL_CUTOFF,
                "payment_day": 2,
                "credit_limit": Decimal("15000000"),
            }
        )
        super().__init__([card])

    async def get_all_status(
        self, user_id: UserId, as_of: date | None = None, **kwargs: object
    ) -> list[CreditCardStatus]:
        return [
            CreditCardStatus(
                card=self._cards[0],
                cycle_start=date(2026, 9, 20),
                cycle_end=date(2026, 10, 19),
                spent_cycle=Decimal("993849"),
                balance=Decimal("10573212"),
                available=Decimal("4426788"),
                utilization=70.5,
                next_payment_date=date(2026, 10, 2),
                cycle_payment_date=date(2026, 11, 2),
                statement_start=date(2026, 8, 20),
                statement_end=date(2026, 9, 19),
                statement_amount=Decimal("9579363"),
            )
        ]


@dataclass
class Call:
    phase: int
    name: str
    arguments: dict[str, Any]
    result: str = ""


@dataclass
class RecordingToolkit:
    """Real ``CardToolkit`` for card tools; records every other call as a stub."""

    cards: CardToolkit
    calls: list[Call] = field(default_factory=list)
    phase: int = 1

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return ALL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: str) -> str:
        call = Call(self.phase, name, arguments)
        if name == QUERY_CARDS_TOOL or name in ALLOWED_WRITES:
            call.result = await self.cards.dispatch(name, arguments, user_id)
        else:
            call.result = "Herramienta no disponible en esta evaluación."
        if name != QUERY_CARDS_TOOL:
            self.calls.append(call)
        return call.result

    def in_phase(self, phase: int, name: str) -> list[Call]:
        return [c for c in self.calls if c.phase == phase and c.name == name]


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class RunResult:
    outcome: Outcome
    same_turn_confirms: int
    # update_card re-called in the "sí" turn (the model re-proposes instead of
    # confirming) and, of those runs, how many still ended up confirmed.
    phase2_updates: int
    phase2_update_runs_confirmed: int


def _new_world() -> tuple[RappiCardService, RecordingToolkit]:
    """A fresh card service + schedule service over an RPC-faithful pending store."""
    service = RappiCardService()
    pending = PendingActionService(FakePendingActionRepository())
    toolkit = RecordingToolkit(CardToolkit(service, CardScheduleChangeService(service, pending)))
    return service, toolkit


def _is_fallback(reply: str) -> bool:
    return reply.startswith(FALLBACK_REPLY_PREFIX)


def _stray_tool(toolkit: RecordingToolkit) -> bool:
    return any(
        c.name not in ALLOWED_WRITES and not c.name.startswith(READ_ONLY_PREFIXES)
        for c in toolkit.calls
    )


def _proposed_ok(case: EvalCase, reply: str) -> bool:
    """The turn-1 reply surfaces a proposal/question and does not deflect to the bank."""
    surfaced = bool(case.proposal.search(reply)) or "?" in reply
    return surfaced and not REFUSAL.search(reply)


def _judge_request(
    case: EvalCase,
    service: RappiCardService,
    toolkit: RecordingToolkit,
    reply1: str,
    reply2: str,
) -> Outcome:
    if _is_fallback(reply1) or _is_fallback(reply2):
        return Outcome.FALLBACK
    if _stray_tool(toolkit):
        return Outcome.FAIL
    proposals = toolkit.in_phase(1, UPDATE_CARD_TOOL)
    proposed = (
        bool(proposals)
        and all(
            c.arguments.get("new_cutoff_day") in case.accepted_cutoffs
            and c.arguments.get("new_payment_day") is None
            for c in proposals
        )
        and any(c.result.startswith(PROPOSAL_PREFIX) for c in proposals)
    )
    confirmed = any(
        c.result.startswith(APPLIED_PREFIX) for c in toolkit.in_phase(2, CONFIRM_CARD_CHANGE_TOOL)
    )
    ends_right = service._cards[0].cutoff_day in case.accepted_cutoffs
    ok = proposed and confirmed and ends_right and _proposed_ok(case, reply1)
    return Outcome.PASS if ok else Outcome.FAIL


def _judge_statement(
    case: EvalCase, service: RappiCardService, toolkit: RecordingToolkit, reply: str
) -> Outcome:
    if _is_fallback(reply):
        return Outcome.FALLBACK
    unchanged = service._cards[0].cutoff_day == INITIAL_CUTOFF
    ok = unchanged and not _stray_tool(toolkit) and _proposed_ok(case, reply)
    return Outcome.PASS if ok else Outcome.FAIL


async def _turn(
    toolkit: RecordingToolkit,
    phase: int,
    history: list[Message],
    message: str,
    gate: asyncio.Semaphore,
) -> str:
    """Run one chat turn under its own bound ``TurnContext`` (fresh turn_id)."""
    toolkit.phase = phase
    turn = TurnContext(
        turn_id=f"eval-turn-{uuid.uuid4().hex}", conversation_id=EVAL_CONVERSATION_ID
    )
    async with gate:
        try:
            with bound_turn(turn):
                return await _run_tool_loop(
                    get_llm_complex(), toolkit, history, message, EVAL_USER_ID, "", EVAL_TODAY
                )
        except Exception as e:  # noqa: BLE001 - script boundary: count it as a fallback.
            return f"{FALLBACK_REPLY_PREFIX} ({type(e).__name__}: {e})"


async def _run_once(
    name: str, case: EvalCase, history: list[Message], gate: asyncio.Semaphore, dump: Path
) -> RunResult:
    service, toolkit = _new_world()
    reply1 = await _turn(toolkit, 1, history, case.message, gate)
    reply2 = ""
    if case.kind is CaseKind.REQUEST:
        followup = [
            *history,
            Message(MessageRole.USER, case.message),
            Message(MessageRole.ASSISTANT, reply1),
        ]
        reply2 = await _turn(toolkit, 2, followup, CONFIRMATION_MESSAGE, gate)
        outcome = _judge_request(case, service, toolkit, reply1, reply2)
    else:
        outcome = _judge_statement(case, service, toolkit, reply1)
    # Confirm attempts in the SAME turn as the proposal: the code must make them no-ops.
    same_turn = toolkit.in_phase(1, CONFIRM_CARD_CHANGE_TOOL)
    if any(c.result.startswith(APPLIED_PREFIX) for c in same_turn):
        outcome = Outcome.FAIL  # the gate would have leaked
    phase2_updates = len(toolkit.in_phase(2, UPDATE_CARD_TOOL))
    confirmed_after_update = int(
        phase2_updates > 0
        and any(
            c.result.startswith(APPLIED_PREFIX)
            for c in toolkit.in_phase(2, CONFIRM_CARD_CHANGE_TOOL)
        )
    )
    record = {
        "case": name,
        "phase2_update_card_calls": phase2_updates,
        "confirmed_despite_phase2_update": bool(confirmed_after_update),
        "kind": case.kind.value,
        "with_history": bool(history),
        "outcome": outcome.value,
        "same_turn_confirms": len(same_turn),
        "final_cutoff": service._cards[0].cutoff_day,
        "tool_calls": [
            {"phase": c.phase, "name": c.name, "args": c.arguments, "result": c.result[:200]}
            for c in toolkit.calls
        ],
        "reply_turn1": reply1,
        "reply_turn2": reply2,
    }
    with dump.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return RunResult(outcome, len(same_turn), phase2_updates, confirmed_after_update)


async def main(runs: int, dump: Path) -> None:
    dump.write_text("", encoding="utf-8")
    print(f"Card cutoff eval — {runs} run(s) per case; runs dumped to {dump}\n")
    gate = asyncio.Semaphore(MAX_CONCURRENCY)
    for name, case in CASES.items():
        for label, history in (("sin historial", []), ("con historial", ASTRID_HISTORY)):
            results = await asyncio.gather(
                *[_run_once(name, case, history, gate, dump) for _ in range(runs)]
            )
            outcomes = [r.outcome for r in results]
            passed = outcomes.count(Outcome.PASS)
            fallbacks = outcomes.count(Outcome.FALLBACK)
            same_turn = sum(r.same_turn_confirms for r in results)
            p2_updates = sum(r.phase2_updates for r in results)
            p2_ok = sum(r.phase2_update_runs_confirmed for r in results)
            print(
                f"{name:<12} {case.kind.value:<9} {label:<14} {passed}/{runs} "
                f"({passed / runs:.0%})  fallback={fallbacks}  same-turn-confirms={same_turn}"
                f"  phase2-update_card={p2_updates} (confirmed anyway: {p2_ok})"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10, help="runs per case (default 10)")
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP, help="JSONL file for all runs")
    args = parser.parse_args()
    asyncio.run(main(args.runs, args.dump))
