"""Offline eval: after a statement REPORT, does Safi register only what is missing?

Runs the real tool-agent loop with the real LLM over a recording toolkit exposing ALL
tool schemas (mutating tools are recorded and answered with a fake success; reads answer
"no data"). The history is the REAL ``_format_report`` output for Astrid's Nu statement:
14 lines, 11 already registered (10 charges + the card payment) and 3 missing
(Euro Arkadia $387.195, Prosalco $90.000, Bold $78.000). Cases:

* "sí": exactly 3 ``register_transaction`` calls with the 3 missing amounts, no
  ``pay_card`` and no other write (the already-registered lines are never re-registered).
* "el de Prosalco es salud": the same 3 calls, Prosalco with category salud, and the
  reply must not re-ask a category/card/payment question.
* "es de Nu" after a report that still asks how it was paid: the 3 calls register on
  credit with card Nu and nothing is asked again.
* a report where everything is already registered + "sí": ZERO write calls.

Reports per case the pass rate, ``pass_without_guard`` (passes where the reply was not the
false-claim guard's replacement) and ``guard_fired`` like ``eval_false_claims.py``. Every run
is dumped to a JSONL file. Costs LLM calls; NOT part of CI or pytest.

Run from project root:
    uv run python scripts/eval_ingestion_verify.py --runs 10
"""

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # allow arrows/emoji in the console

from app.agents.nodes.action_claims import FALSE_CLAIM_REPLY, MUTATING_TOOLS
from app.agents.nodes.image_ingestion import (
    ExtractedMovement,
    ExtractionResult,
    _format_report,
    _to_statement_line,
)
from app.agents.nodes.tool_agent import DUPLICATE_WRITE_RESULT, _run_tool_loop
from app.agents.tools.analysis_tools import ANALYSIS_TOOL_SCHEMAS
from app.agents.tools.budget_tools import BUDGET_TOOL_SCHEMAS
from app.agents.tools.card_tools import CARD_TOOL_SCHEMAS, PAY_CARD_TOOL
from app.agents.tools.category_tools import CATEGORY_TOOL_SCHEMAS
from app.agents.tools.goal_tools import GOAL_TOOL_SCHEMAS
from app.agents.tools.movement_tools import MOVEMENT_TOOL_SCHEMAS
from app.agents.tools.profile_tools import PROFILE_TOOL_SCHEMAS
from app.agents.tools.recurring_tools import RECURRING_TOOL_SCHEMAS
from app.agents.tools.transaction_tools import REGISTER_TRANSACTION_TOOL, TRANSACTION_TOOL_SCHEMAS
from app.shared.dependencies import get_llm_complex
from app.shared.interfaces.llm import Message, MessageRole
from app.shared.text_match import normalize
from app.shared.types import IngestionIntent, StatementLineKind
from app.src.analysis.models import ReconciledLine, ReconciliationResult

EVAL_USER_ID = "eval-user"
EVAL_TODAY = date(2026, 10, 30)
MAX_CONCURRENCY = 3
FALLBACK_REPLY_PREFIX = "Lo siento, no pude completar la operación"
DEFAULT_DUMP = Path(__file__).parent / ".eval_ingestion_verify_runs.jsonl"
FAKE_SUCCESS = "Hecho: la operación se guardó correctamente."
FAKE_READ = "Sin datos."
CARD = "Nu"
VERIFY_NOTE = "[imagen] Valida que todos estos movimientos de nu estén registrados"

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

# Astrid's statement: description, amount, day of October 2026.
_STATEMENT: tuple[tuple[str, str, int], ...] = (
    ("Flypass", "5700", 26),
    ("Tostao Cafe Y Pan", "6000", 25),
    ("Euro Arkadia", "387195", 25),
    ("Universidad Eafit", "10800", 25),
    ("Flypass", "5200", 25),
    ("la Migueria", "29600", 24),
    ("City Park Medellin", "33000", 24),
    ("Prosalco Las Vegas", "90000", 24),
    ("Flypass", "3400", 24),
    ("Bold Sa*Los Cham", "78000", 24),
    ("El Domicilio de Rodeo", "21000", 23),
    ("El Domicilio de Rodeo", "19500", 21),
    ("Flypass", "3600", 20),
)
MISSING: dict[str, Decimal] = {
    "Euro Arkadia": Decimal("387195"),
    "Prosalco Las Vegas": Decimal("90000"),
    "Bold Sa*Los Cham": Decimal("78000"),
}
PROSALCO = "Prosalco Las Vegas"
EXPECTED_REGISTRATIONS = len(MISSING)
CATEGORY_SALUD = "salud"
# A question the model must not repeat once the user answered it.
_SENTENCE_END = re.compile(r"[.!:\n]")
_REASK_KEYWORDS = ("tarjeta", "categor", "efectivo", "crédito", "credito", "pagaste")


def _movements(known_payment: bool) -> list[ExtractedMovement]:
    """The 14 extracted movements; ``known_payment`` False leaves method/card unknown."""
    charges = [
        ExtractedMovement(
            description=description,
            amount=Decimal(amount),
            date=f"2026-10-{day:02d}",
            payment_method="credito" if known_payment else None,
            card=CARD if known_payment else None,
        )
        for description, amount, day in _STATEMENT
    ]
    payment = ExtractedMovement(
        description="Gracias por tu pago",
        amount=Decimal("1303500"),
        transaction_type=StatementLineKind.CARD_PAYMENT,
        date="2026-10-19",
        card=CARD,
    )
    return [*charges, payment]


def _report(missing_names: frozenset[str], known_payment: bool) -> str:
    """The production report for the statement with ``missing_names`` still unregistered."""
    movements = _movements(known_payment)
    lines = [_to_statement_line(m) for m in movements]
    reconciliation = ReconciliationResult(
        matched=[
            ReconciledLine(
                line=line,
                matched_label=CARD
                if line.kind is StatementLineKind.CARD_PAYMENT
                else line.description,
                matched_date=line.date,
            )
            for line in lines
            if line.description not in missing_names
        ],
        missing=[line for line in lines if line.description in missing_names],
    )
    return _format_report(
        ExtractionResult(movements=movements), reconciliation, IngestionIntent.VERIFY
    )


def _history(report: str) -> tuple[Message, ...]:
    return (Message(MessageRole.USER, VERIFY_NOTE), Message(MessageRole.ASSISTANT, report))


class CaseKind(StrEnum):
    REGISTER_MISSING = "register"  # "sí": the 3 missing, nothing else
    CATEGORY_FIX = "category_fix"  # "el de Prosalco es salud": 3 calls, one categorized
    CARD_ANSWER = "card_answer"  # "es de Nu": 3 credit/Nu calls, no repeated question
    ALL_REGISTERED = "all_registered"  # nothing missing: a "sí" writes nothing


@dataclass(frozen=True)
class EvalCase:
    message: str
    kind: CaseKind
    history: tuple[Message, ...]


CASES: dict[str, EvalCase] = {
    "si_tras_reporte": EvalCase(
        "sí",
        CaseKind.REGISTER_MISSING,
        _history(_report(frozenset(MISSING), known_payment=True)),
    ),
    "prosalco_es_salud": EvalCase(
        "el de Prosalco es salud",
        CaseKind.CATEGORY_FIX,
        _history(_report(frozenset(MISSING), known_payment=True)),
    ),
    "es_de_nu": EvalCase(
        "es de Nu",
        CaseKind.CARD_ANSWER,
        _history(_report(frozenset(MISSING), known_payment=False)),
    ),
    "si_con_todo_registrado": EvalCase(
        "sí",
        CaseKind.ALL_REGISTERED,
        _history(_report(frozenset(), known_payment=True)),
    ),
}


@dataclass
class Call:
    name: str
    arguments: dict[str, Any]
    result: str = ""


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
        """Mirror the real tools' wording: a registration echoes what it saved."""
        if name not in MUTATING_TOOLS:
            return FAKE_READ
        if name == REGISTER_TRANSACTION_TOOL:  # same shape as TransactionToolkit
            method = f", {arguments['payment_method']}" if arguments.get("payment_method") else ""
            return (
                f"✅ Registré: {arguments.get('description')} — ${arguments.get('amount')} "
                f"({arguments.get('category', 'otros')}, {arguments.get('transaction_date')}"
                f"{method})."
            )
        return FAKE_SUCCESS

    def writes(self) -> list[Call]:
        return [c for c in self.calls if c.name in MUTATING_TOOLS]

    def registrations(self) -> list[Call]:
        return [c for c in self.calls if c.name == REGISTER_TRANSACTION_TOOL]

    def card_payments(self) -> list[Call]:
        return [c for c in self.calls if c.name == PAY_CARD_TOOL]


class CountingLLM:
    """Proxy over the real LLM that keeps the last messages the model was shown.

    The loop never dispatches a skipped repeat, so the toolkit can't see it; the model's
    own conversation shows how many times it was told "no la ejecuté otra vez".
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.last_messages: list[Message] = []

    async def generate_with_tools(self, messages: Any, tools: Any, config: Any = None) -> Any:
        self.last_messages = list(messages)
        return await self._inner.generate_with_tools(messages, tools, config)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def duplicate_write_skips(self) -> int:
        return sum(m.content.count(DUPLICATE_WRITE_RESULT) for m in self.last_messages)


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class RunResult:
    outcome: Outcome
    guard_fired: bool
    duplicate_write_skips: int = 0

    @property
    def pass_without_guard(self) -> bool:
        return self.outcome is Outcome.PASS and not self.guard_fired


def _amount(call: Call) -> Decimal | None:
    try:
        return Decimal(str(call.arguments.get("amount")))
    except InvalidOperation:
        return None


def _registers_exactly_the_missing(toolkit: RecordingToolkit) -> bool:
    amounts = sorted(a for a in (_amount(c) for c in toolkit.registrations()) if a is not None)
    return (
        amounts == sorted(MISSING.values())
        and len(toolkit.registrations()) == EXPECTED_REGISTRATIONS
        and len(toolkit.writes()) == EXPECTED_REGISTRATIONS  # no pay_card, nothing else
        and not toolkit.card_payments()
    )


def _re_asks(reply: str) -> bool:
    """True if the reply asks again about the card, category or payment method."""
    # Only the sentence that ends in "?" counts, not the statements before it.
    questions = [_SENTENCE_END.split(q)[-1] for q in normalize(reply).split("?")[:-1]]
    return any(keyword in question for question in questions for keyword in _REASK_KEYWORDS)


def _prosalco_is_salud(toolkit: RecordingToolkit) -> bool:
    return any(
        _amount(c) == MISSING[PROSALCO]
        and normalize(str(c.arguments.get("category", ""))) == CATEGORY_SALUD
        for c in toolkit.registrations()
    )


def _all_on_credit_with_card(toolkit: RecordingToolkit) -> bool:
    return all(
        c.arguments.get("payment_method") == "credito"
        and CARD.lower() in normalize(str(c.arguments.get("card_name", "")))
        for c in toolkit.registrations()
    )


def _judge(case: EvalCase, toolkit: RecordingToolkit, reply: str) -> Outcome:
    if reply.startswith(FALLBACK_REPLY_PREFIX):
        return Outcome.FALLBACK
    if reply == FALSE_CLAIM_REPLY:
        return Outcome.FAIL
    if case.kind is CaseKind.ALL_REGISTERED:
        ok = not toolkit.writes()
    elif case.kind is CaseKind.REGISTER_MISSING:
        ok = _registers_exactly_the_missing(toolkit)
    elif case.kind is CaseKind.CATEGORY_FIX:
        ok = (
            _registers_exactly_the_missing(toolkit)
            and _prosalco_is_salud(toolkit)
            and not _re_asks(reply)
        )
    else:
        ok = (
            _registers_exactly_the_missing(toolkit)
            and _all_on_credit_with_card(toolkit)
            and not _re_asks(reply)
        )
    return Outcome.PASS if ok else Outcome.FAIL


async def _run_once(name: str, case: EvalCase, gate: asyncio.Semaphore, dump: Path) -> RunResult:
    toolkit = RecordingToolkit()
    llm = CountingLLM(get_llm_complex())
    async with gate:
        try:
            reply = await _run_tool_loop(
                llm,
                toolkit,
                list(case.history),
                case.message,
                EVAL_USER_ID,
                "",
                EVAL_TODAY,
            )
        except Exception as e:  # noqa: BLE001 - script boundary: count it as a fallback.
            reply = f"{FALLBACK_REPLY_PREFIX} ({type(e).__name__}: {e})"
    outcome = _judge(case, toolkit, reply)
    guard_fired = reply == FALSE_CLAIM_REPLY
    record = {
        "case": name,
        "kind": case.kind.value,
        "message": case.message,
        "outcome": outcome.value,
        "guard_fired": guard_fired,
        "duplicate_write_skips": llm.duplicate_write_skips(),
        "tool_calls": [{"name": c.name, "args": c.arguments} for c in toolkit.calls],
        "reply": reply,
    }
    with dump.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return RunResult(outcome, guard_fired, llm.duplicate_write_skips())


async def main(runs: int, dump: Path, only: str | None = None) -> None:
    if only is None:  # a single-case run appends, so it never wipes earlier runs
        dump.write_text("", encoding="utf-8")
    print(f"Ingestion-verify eval — {runs} run(s) per case; runs dumped to {dump}\n")
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
        skips = sum(r.duplicate_write_skips for r in results)
        print(
            f"{name:<26} {case.kind.value:<15} {passed}/{runs} ({passed / runs:.0%})  "
            f"pass_without_guard={clean}  guard_fired={guard_fired}  fallback={fallbacks}  "
            f"duplicate_write_skips={skips}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10, help="runs per case (default 10)")
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP, help="JSONL file for all runs")
    parser.add_argument("--case", choices=sorted(CASES), help="run only this case")
    args = parser.parse_args()
    asyncio.run(main(args.runs, args.dump, args.case))
