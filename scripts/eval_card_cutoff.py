"""Offline eval: does Safi change a card's cutoff day from billing-period wording?

Runs the real tool-agent loop with the real LLM and the REAL ``CardToolkit`` over an
in-memory card service (one card "Rappi", corte 19, pago 2, a realistic balance), so
``query_cards`` / ``update_card`` produce production-shaped text. Every other tool is
stubbed; mutating calls are recorded and count as failures. Reports, per phrasing and
with/without a prior history resembling Astrid's real transcript, how often the agent
proposes or applies the right cutoff day. Every run is dumped to a JSONL file.
Costs LLM calls; NOT part of CI or pytest.

Run from project root:
    uv run python scripts/eval_card_cutoff.py --runs 10
"""

import argparse
import asyncio
import json
import re
import sys
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
from app.shared.types import UserId
from app.src.cards.models import CreditCardStatus
from tests.unit.agents.test_card_tools import FakeCardService, _card

EVAL_USER_ID = "eval-user"
EVAL_TODAY = date(2026, 10, 1)
MAX_CONCURRENCY = 3
FALLBACK_REPLY_PREFIX = "Lo siento, no pude completar la operación"
DEFAULT_DUMP = Path(__file__).parent / ".eval_card_cutoff_runs.jsonl"
# Tools that only read data; any other tool besides update_card counts as a failure.
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


@dataclass(frozen=True)
class EvalCase:
    message: str
    accepted_cutoffs: frozenset[int]
    proposal: re.Pattern[str]


QUESTION_ABOUT_20 = r"¿[^?]*(cambi|actualiz)[^?]*\b20\b[^?]*\?"
PROPOSES_20 = re.compile(rf"→\s*20\b|{QUESTION_ABOUT_20}", re.IGNORECASE)
PROPOSES_MONTH_END = re.compile(
    r"→\s*(30|31)\b|fin de mes|último día|¿[^?]*(cambi|actualiz)[^?]*\b(30|31)\b[^?]*\?",
    re.IGNORECASE,
)
# Any refusal/deflection fails the run unless update_card was actually called.
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
            update={"cutoff_day": 19, "payment_day": 2, "credit_limit": Decimal("15000000")}
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
class RecordingToolkit:
    """Real ``CardToolkit`` for query/update; records every other call as a stub."""

    cards: CardToolkit = field(default_factory=lambda: CardToolkit(RappiCardService()))
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    update_results: list[str] = field(default_factory=list)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return ALL_SCHEMAS

    async def dispatch(self, name: str, arguments: dict[str, Any], user_id: str) -> str:
        if name == QUERY_CARDS_TOOL:
            return await self.cards.dispatch(name, arguments, user_id)
        self.calls.append((name, arguments))
        if name == UPDATE_CARD_TOOL:
            result = await self.cards.dispatch(name, arguments, user_id)
            self.update_results.append(result)
            return result
        return "Herramienta no disponible en esta evaluación."


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    FALLBACK = "fallback"


def _judge(case: EvalCase, toolkit: RecordingToolkit, reply: str) -> Outcome:
    if reply.startswith(FALLBACK_REPLY_PREFIX):
        return Outcome.FALLBACK
    if any(
        name != UPDATE_CARD_TOOL and not name.startswith(READ_ONLY_PREFIXES)
        for name, _ in toolkit.calls
    ):
        return Outcome.FAIL
    updates = [args for name, args in toolkit.calls if name == UPDATE_CARD_TOOL]
    if updates:
        right = all(
            u.get("new_cutoff_day") in case.accepted_cutoffs and u.get("new_payment_day") is None
            for u in updates
        )
        # A call the real toolkit rejected (e.g. unknown card name) changed nothing.
        applied = any(r.startswith("✏️ Actualicé") for r in toolkit.update_results)
        return Outcome.PASS if right and applied else Outcome.FAIL
    if REFUSAL.search(reply):
        return Outcome.FAIL
    return Outcome.PASS if case.proposal.search(reply) else Outcome.FAIL


async def _run_once(
    name: str, case: EvalCase, history: list[Message], gate: asyncio.Semaphore, dump: Path
) -> Outcome:
    toolkit = RecordingToolkit()
    async with gate:
        try:
            reply = await _run_tool_loop(
                get_llm_complex(), toolkit, history, case.message, EVAL_USER_ID, "", EVAL_TODAY
            )
        except Exception as e:  # noqa: BLE001 - script boundary: count it as a fallback.
            reply = f"{FALLBACK_REPLY_PREFIX} ({type(e).__name__}: {e})"
    outcome = _judge(case, toolkit, reply)
    record = {
        "case": name,
        "with_history": bool(history),
        "outcome": outcome.value,
        "tool_calls": [{"name": n, "args": a} for n, a in toolkit.calls],
        "reply": reply,
    }
    with dump.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return outcome


async def main(runs: int, dump: Path) -> None:
    dump.write_text("", encoding="utf-8")
    print(f"Card cutoff eval — {runs} run(s) per case; runs dumped to {dump}\n")
    gate = asyncio.Semaphore(MAX_CONCURRENCY)
    for name, case in CASES.items():
        for label, history in (("sin historial", []), ("con historial", ASTRID_HISTORY)):
            outcomes = await asyncio.gather(
                *[_run_once(name, case, history, gate, dump) for _ in range(runs)]
            )
            passed = outcomes.count(Outcome.PASS)
            fallbacks = outcomes.count(Outcome.FALLBACK)
            print(
                f"{name:<12} {label:<14} {passed}/{runs} ({passed / runs:.0%})"
                f"  fallback={fallbacks}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10, help="runs per case (default 10)")
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP, help="JSONL file for all runs")
    args = parser.parse_args()
    asyncio.run(main(args.runs, args.dump))
