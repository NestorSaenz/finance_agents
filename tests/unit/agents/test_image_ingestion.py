"""Unit tests for the image ingestion service (vision LLM mocked)."""

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest
from postgrest.exceptions import APIError

from app.agents.nodes.image_ingestion import (
    PROPOSAL_CONFIRM,
    PROPOSAL_HEADER,
    ExtractedMovement,
    ExtractionResult,
    ImageIngestionService,
    _format_report,
    _reclassify_card_payments,
    detect_ingestion_intent,
)
from app.core.exceptions import DatabaseQueryError
from app.shared.clock import bound_today
from app.shared.types import IngestionIntent, StatementLineKind
from app.src.analysis.models import ReconciledLine, ReconciliationResult, StatementLine
from tests.fakes import FakeLLM, FakeStatementReconciler

pytestmark = pytest.mark.asyncio

USER = "u1"

def _service(llm: FakeLLM, reconciler: FakeStatementReconciler | None = None) -> ImageIngestionService:
    return ImageIngestionService(llm, reconciler or FakeStatementReconciler())


_VALID_JSON = """
{
  "movements": [
    {"description": "Supermercado", "amount": 200000, "transaction_type": "expense",
     "date": "2026-07-01", "category": "alimentacion", "payment_method": "efectivo"},
    {"description": "Poda jardín", "amount": 50000, "transaction_type": "expense",
     "date": null, "category": "jardinería", "payment_method": null}
  ],
  "questions": ["¿'M' significa mercado?"],
  "notes": null
}
"""


async def test_propose_lists_movements_and_asks_confirmation() -> None:
    service = _service(FakeLLM(_VALID_JSON))

    proposal = await service.propose(b"\x89PNG-bytes", "image/png", USER)

    assert "Supermercado" in proposal
    assert "$200.000" in proposal  # Colombian format: dot thousands separator
    assert "jardinería" in proposal  # custom category preserved in the proposal
    assert "¿'M' significa mercado?" not in proposal  # only the payment question is kept
    assert "¿Los registro tal cual?" in proposal  # asks before saving


async def test_propose_sends_image_to_the_llm() -> None:
    fake = FakeLLM(_VALID_JSON)
    service = _service(fake)

    await service.propose(b"rawbytes", "image/jpeg", USER, user_context="El usuario se llama Ana.")

    # The user message carries the image part; the system prompt carries the context.
    user_message = fake.calls[0][-1]
    assert user_message.images is not None
    assert user_message.images[0].data == b"rawbytes"
    assert user_message.images[0].mime_type == "image/jpeg"
    assert any("Ana" in m.content for m in fake.calls[0])


async def test_propose_handles_no_movements() -> None:
    service = _service(FakeLLM('{"movements": [], "questions": [], "notes": null}'))

    proposal = await service.propose(b"x", "image/png", USER)

    assert "No encontré movimientos" in proposal


async def test_propose_tolerates_code_fenced_json() -> None:
    fenced = "```json\n" + _VALID_JSON + "\n```"
    service = _service(FakeLLM(fenced))

    proposal = await service.propose(b"x", "image/png", USER)

    assert "Supermercado" in proposal


async def test_propose_degrades_on_unparseable_output() -> None:
    service = _service(FakeLLM("lo siento, no es json"))

    proposal = await service.propose(b"x", "image/png", USER)

    assert "No pude leer el archivo" in proposal


async def test_propose_asks_payment_method_when_missing() -> None:
    # Expense with no payment_method and a question that isn't about payment.
    json_no_method = """
    {"movements": [{"description": "Factura gimnasio", "amount": 199966,
      "transaction_type": "expense", "category": "gimnasio", "payment_method": null}],
     "questions": [], "notes": null}
    """
    service = _service(FakeLLM(json_no_method))

    proposal = await service.propose(b"x", "application/pdf", USER)

    assert "efectivo" in proposal.lower() and "crédito" in proposal.lower()


async def test_propose_never_asks_for_a_category() -> None:
    # No category → Safi categorizes by itself; the user is not asked per line.
    json_no_category = """
    {"movements": [{"description": "SPORT LINE S.A.", "amount": 199966,
      "transaction_type": "expense", "category": null, "payment_method": "efectivo"}],
     "questions": ["¿En qué categoría clasifico SPORT LINE?"], "notes": null}
    """
    service = _service(FakeLLM(json_no_category))

    proposal = await service.propose(b"x", "application/pdf", USER)

    assert "categoría automática" in proposal
    assert "clasifico" not in proposal
    assert "Antes de registrar" not in proposal  # payment method is known: no question


async def test_propose_does_not_duplicate_payment_question() -> None:
    # The model already asked about the method → no extra deterministic question.
    json_asked = """
    {"movements": [{"description": "Compra", "amount": 50000,
      "transaction_type": "expense", "payment_method": null}],
     "questions": ["¿Lo pagaste en efectivo o con tarjeta?"], "notes": null}
    """
    service = _service(FakeLLM(json_asked))

    proposal = await service.propose(b"x", "image/png", USER)

    assert proposal.lower().count("efectivo") == 1  # not asked twice


async def test_propose_corrects_misread_statement_year() -> None:
    raw = """
    {"movements": [
      {"description": "Rappi", "amount": 30000, "transaction_type": "expense",
       "date": "2023-09-04", "category": "comida", "payment_method": "credito"},
      {"description": "Uber", "amount": 12000, "transaction_type": "expense",
       "date": "2026-10-15", "category": "transporte", "payment_method": "credito"},
      {"description": "Raro", "amount": 1000, "transaction_type": "expense",
       "date": "ayer", "category": "otros", "payment_method": "credito"}],
     "questions": [], "notes": null}
    """
    fake = FakeLLM(raw)
    with bound_today(date(2026, 10, 20)):
        proposal = await _service(fake).propose(b"x", "image/png", USER)

    assert "2026-09-04" in proposal and "2023-09-04" not in proposal
    assert "2026-10-15" in proposal  # plausible date untouched
    assert "ayer" in proposal  # unparseable left as is
    system = fake.calls[0][0].content
    assert "2026-10-20" in system  # today is given to the extractor
    assert "año de hoy" in system


# --- intent detection --------------------------------------------------------


@pytest.mark.parametrize(
    ("note", "expected"),
    [
        ("Valida que todos estos movimientos de nu estén registrados", IngestionIntent.VERIFY),
        ("", IngestionIntent.REGISTER),
        ("son de mi tarjeta Nu", IngestionIntent.REGISTER),
        ("revisa y registra los que falten", IngestionIntent.VERIFY),
        ("¿Cuáles faltan?", IngestionIntent.VERIFY),
        ("registra esto", IngestionIntent.REGISTER),
        ("qué movimientos no he registrado", IngestionIntent.VERIFY),
        ("dime cuáles están sin registrar", IngestionIntent.VERIFY),
        ("hay algo por registrar de esta imagen?", IngestionIntent.VERIFY),
    ],
)
def test_detect_ingestion_intent(note: str, expected: IngestionIntent) -> None:
    assert detect_ingestion_intent(note) == expected


# --- card payment reclassifier -----------------------------------------------


def _movement(
    description: str,
    amount: str,
    ttype: str = "expense",
    payment_method: str | None = None,
    card: str | None = None,
    day: str = "2026-10-24",
) -> ExtractedMovement:
    return ExtractedMovement(
        description=description,
        amount=Decimal(amount),
        transaction_type=ttype,
        date=day,
        payment_method=payment_method,
        card=card,
    )


def test_credit_statement_payment_received_becomes_card_payment() -> None:
    result = ExtractionResult(
        movements=[
            _movement("Flypass", "5700", payment_method="credito", card="Nu"),
            _movement("Gracias por tu pago", "1303500", ttype="income"),
        ]
    )

    fixed = _reclassify_card_payments(result)

    assert fixed.movements[0].transaction_type == "expense"
    assert fixed.movements[1].transaction_type == StatementLineKind.CARD_PAYMENT
    assert fixed.movements[1].card == "Nu"  # inherited from the statement's card


def test_refund_abono_on_a_credit_statement_is_not_a_card_payment() -> None:
    result = ExtractionResult(
        movements=[
            _movement("Flypass", "5700", payment_method="credito", card="Nu"),
            _movement("Abono por devolución", "45000", ttype="income"),
        ]
    )

    fixed = _reclassify_card_payments(result)

    assert fixed.movements[1].transaction_type == "income"


def test_abono_a_tarjeta_on_a_credit_statement_is_a_card_payment() -> None:
    result = ExtractionResult(
        movements=[
            _movement("Flypass", "5700", payment_method="credito", card="Nu"),
            _movement("Abono a tarjeta", "50000", ttype="income"),
        ]
    )

    assert _reclassify_card_payments(result).movements[1].transaction_type == "card_payment"


def test_an_expense_is_never_reclassified() -> None:
    result = ExtractionResult(
        movements=[
            _movement("Flypass", "5700", payment_method="credito", card="Nu"),
            _movement("Pago recibido", "50000", ttype="expense"),
        ]
    )

    assert _reclassify_card_payments(result).movements[1].transaction_type == "expense"


async def test_note_about_the_card_does_not_reclassify_a_savings_deposit() -> None:
    raw = (
        '{"movements": [{"description": "Abono nómina", "amount": 3000000,'
        ' "transaction_type": "income", "date": "2026-10-28"}]}'
    )
    reconciler = FakeStatementReconciler()

    await _service(FakeLLM(raw), reconciler).propose(
        b"x", "image/png", USER, user_note="revisa si pagué la tarjeta"
    )

    assert reconciler.calls[0][1][0].kind == StatementLineKind.INCOME


def test_savings_statement_abono_stays_income() -> None:
    result = ExtractionResult(
        movements=[
            _movement("Abono nómina", "3000000", ttype="income"),
            _movement("Retiro cajero", "100000"),
        ]
    )

    fixed = _reclassify_card_payments(result)

    assert fixed.movements[0].transaction_type == "income"


# --- report ------------------------------------------------------------------

_ASTRID: list[tuple[str, str, int]] = [
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
]
_MISSING = {"Euro Arkadia", "Prosalco Las Vegas", "Bold Sa*Los Cham"}


def _astrid_movements() -> list[ExtractedMovement]:
    charges = [
        _movement(d, a, payment_method="credito", card="Nu", day=f"2026-10-{day:02d}")
        for d, a, day in _ASTRID
    ]
    payment = _movement(
        "Gracias por tu pago", "1303500", ttype="card_payment", card="Nu", day="2026-10-19"
    )
    return [*charges, payment]


def _line_of(m: ExtractedMovement) -> StatementLine:
    kind = (
        StatementLineKind.CARD_PAYMENT
        if m.transaction_type == "card_payment"
        else StatementLineKind.EXPENSE
    )
    return StatementLine(
        description=m.description,
        amount=m.amount,
        date=date.fromisoformat(m.date or ""),
        kind=kind,
        card=m.card,
    )


def _astrid_reconciliation(missing_names: set[str] = _MISSING) -> ReconciliationResult:
    lines = [_line_of(m) for m in _astrid_movements()]
    return ReconciliationResult(
        matched=[
            ReconciledLine(
                line=line,
                matched_label="Nu"
                if line.kind == StatementLineKind.CARD_PAYMENT
                else line.description,
                matched_date=line.date,
            )
            for line in lines
            if line.description not in missing_names
        ],
        missing=[line for line in lines if line.description in missing_names],
    )


def _astrid_report(intent: IngestionIntent = IngestionIntent.VERIFY) -> str:
    result = ExtractionResult(movements=_astrid_movements())
    return _format_report(result, _astrid_reconciliation(), intent)


def test_verify_report_header_and_matched_before_the_marker() -> None:
    report = _astrid_report()

    assert report.startswith("Revisé 14 movimientos contra tus registros: 11 ya están registrados.")
    before = report.split(PROPOSAL_HEADER, 1)[0]
    assert "Flypass" in before and "💳 pago a tu Nu del 19-oct ya registrado" in before
    assert "Euro Arkadia" not in before


def test_marker_block_holds_only_the_missing_lines() -> None:
    block = _astrid_report().split(PROPOSAL_HEADER, 1)[1]

    assert all(name in block for name in _MISSING)
    assert "Flypass" not in block and "Tostao" not in block and "Pago a tarjeta" not in block
    assert block.count("\n- ") == 3
    assert "$387.195" in block and "categoría automática" in block
    assert "Los categorizo yo y te muestro cómo quedaron." in block
    assert block.rstrip().endswith(
        f"{PROPOSAL_CONFIRM} Dime *sí* para guardarlos, o indícame qué corregir."
    )
    assert "Antes de registrar" not in block  # card and method are known


def test_everything_registered_has_no_marker() -> None:
    report = _format_report(
        ExtractionResult(movements=_astrid_movements()),
        _astrid_reconciliation(missing_names=set()),
        IngestionIntent.VERIFY,
    )

    assert "Todos ya están registrados ✅" in report
    assert PROPOSAL_HEADER not in report and PROPOSAL_CONFIRM not in report


def test_register_mode_only_changes_the_wording() -> None:
    report = _astrid_report(IngestionIntent.REGISTER)

    assert report.startswith("Ya tenías 11 de 14 registrados; propongo registrar los restantes.")
    assert report.split(PROPOSAL_HEADER, 1)[1].count("\n- ") == 3  # none re-proposed


def test_unmatched_card_payment_is_rendered_as_a_card_payment() -> None:
    result = ExtractionResult(
        movements=[
            _movement("Gracias por tu pago", "1303500", "card_payment", "credito", "Nu", "2026-10-19")
        ]
    )

    report = _format_report(result)

    assert "- Pago a tarjeta Nu: $1.303.500 (pago de tarjeta, 2026-10-19)" in report


def test_at_most_one_question_and_never_about_categories() -> None:
    result = ExtractionResult(
        movements=[_movement("Compra", "1000"), _movement("Otra", "2000")],
        questions=[
            "¿Qué categoría es Compra?",
            "¿Qué significa Otra?",
            "¿Lo pagaste en efectivo o con tarjeta?",
            "¿Con qué tarjeta?",
        ],
    )

    report = _format_report(result)

    assert report.count("\n- ¿") == 1
    assert "efectivo o con tarjeta" in report
    assert "categoría es" not in report


def test_no_question_when_the_card_is_known() -> None:
    result = ExtractionResult(
        movements=[_movement("Compra", "1000", card="Nu")], questions=["¿Con qué tarjeta?"]
    )

    assert "Antes de registrar" not in _format_report(result)


# --- reconciliation wiring ---------------------------------------------------


async def test_propose_reports_against_the_records_and_passes_the_user() -> None:
    raw = json.dumps(
        {
            "movements": [
                {"description": "Flypass", "amount": 5700, "transaction_type": "expense",
                 "date": "2026-10-26", "payment_method": "credito", "card": "Nu"},
                {"description": "Euro Arkadia", "amount": 387195, "transaction_type": "expense",
                 "date": "2026-10-25", "payment_method": "credito", "card": "Nu"},
                {"description": "Gracias por tu pago", "amount": 1303500,
                 "transaction_type": "income", "date": "2026-10-19", "card": "Nu",
                 "payment_method": "credito"},
            ],
            "questions": [],
            "notes": None,
        }
    )
    reconciler = FakeStatementReconciler()

    with bound_today(date(2026, 10, 30)):
        proposal = await _service(FakeLLM(raw), reconciler).propose(
            b"x", "image/png", USER, user_note="Valida que todos estén registrados"
        )

    [(user_id, lines)] = reconciler.calls
    assert user_id == USER
    # The payment received was reclassified BEFORE reconciling (never an income line).
    assert [line.kind for line in lines] == [
        StatementLineKind.EXPENSE,
        StatementLineKind.EXPENSE,
        StatementLineKind.CARD_PAYMENT,
    ]
    assert proposal.startswith("Revisé 3 movimientos contra tus registros: 0 ya están registrados.")


async def test_line_without_date_is_sent_undated_not_as_today() -> None:
    raw = '{"movements": [{"description": "Compra", "amount": 5000, "payment_method": "efectivo"}]}'
    reconciler = FakeStatementReconciler()

    with bound_today(date(2026, 10, 30)):
        await _service(FakeLLM(raw), reconciler).propose(b"x", "image/png", USER)

    assert reconciler.calls[0][1][0].date is None


@pytest.mark.parametrize(
    "error",
    [
        DatabaseQueryError("select", "boom"),
        APIError({"message": "boom", "code": "500", "details": "", "hint": ""}),
        httpx.ConnectError("down"),
    ],
)
async def test_db_failure_in_register_mode_keeps_the_block_with_a_warning(
    error: Exception,
) -> None:
    service = _service(FakeLLM(_VALID_JSON), FakeStatementReconciler(error=error))

    proposal = await service.propose(b"x", "image/png", USER)

    assert "Ojo: no pude revisar si alguno ya estaba registrado." in proposal
    assert proposal.startswith("Leí 2 movimientos.")
    assert "ninguno estaba registrado" not in proposal
    assert PROPOSAL_HEADER in proposal and "Supermercado" in proposal
    assert PROPOSAL_CONFIRM in proposal


async def test_db_failure_in_verify_mode_proposes_nothing() -> None:
    service = _service(
        FakeLLM(_VALID_JSON), FakeStatementReconciler(error=httpx.ConnectError("down"))
    )

    proposal = await service.propose(
        b"x", "image/png", USER, user_note="valida que estén registrados"
    )

    assert proposal.startswith("Leí 2 movimientos.")
    assert "No pude compararlos con tus registros; inténtalo de nuevo en un momento." in proposal
    assert PROPOSAL_HEADER not in proposal and PROPOSAL_CONFIRM not in proposal


def test_register_mode_with_everything_registered_does_not_propose() -> None:
    report = _format_report(
        ExtractionResult(movements=_astrid_movements()),
        _astrid_reconciliation(missing_names=set()),
        IngestionIntent.REGISTER,
    )

    assert report.startswith("Revisé 14 movimientos: los 14 ya están registrados.")
    assert "propongo" not in report
    assert "Todos ya están registrados ✅" in report
    assert PROPOSAL_HEADER not in report
