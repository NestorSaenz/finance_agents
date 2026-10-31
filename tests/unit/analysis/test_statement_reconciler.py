"""Unit tests for statement reconciliation (pure matcher + the fetching service)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

from app.shared.types import PaymentMethod, StatementLineKind, TransactionType
from app.src.analysis.constants import RECONCILE_WINDOW_DAYS
from app.src.analysis.models import StatementLine
from app.src.analysis.services.statement_reconciler import StatementReconciler, match_lines
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import CardPaymentView
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import Transaction

USER = "u1"
EXPENSE = StatementLineKind.EXPENSE

# Astrid's Nu statement (2026): description, amount, day (October).
_CHARGES: list[tuple[str, str, int]] = [
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


def _line(
    description: str,
    amount: str,
    on: date | None,
    kind: StatementLineKind = EXPENSE,
    card: str | None = "Nu",
) -> StatementLine:
    return StatementLine(
        description=description, amount=Decimal(amount), date=on, kind=kind, card=card
    )


def _tx(
    description: str,
    amount: str,
    on: date,
    ttype: TransactionType = TransactionType.EXPENSE,
    payment_method: PaymentMethod | None = PaymentMethod.CREDITO,
    budget_date: date | None = None,
) -> Transaction:
    return Transaction(
        id=f"tx-{description}-{on}-{amount}",
        user_id=USER,
        amount=Decimal(amount),
        currency="COP",
        transaction_type=ttype,
        description=description,
        category="otros",
        payment_method=payment_method,
        transaction_date=on,
        budget_date=budget_date or on,
        source="manual",
        created_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


def _payment(amount: str, on: date, card: str = "Nu") -> CardPaymentView:
    return CardPaymentView(
        card_id=f"card-{card}", card_name=card, amount=Decimal(amount), payment_date=on
    )


def _astrid_lines() -> list[StatementLine]:
    charges = [_line(d, a, date(2026, 10, day)) for d, a, day in _CHARGES]
    pago = _line("Gracias por tu pago", "1303500", date(2026, 10, 19), StatementLineKind.CARD_PAYMENT)
    return [*charges, pago]


def _astrid_records() -> tuple[list[Transaction], list[CardPaymentView]]:
    txs = [
        _tx(d, a, date(2026, 10, day)) for d, a, day in _CHARGES if d not in _MISSING
    ]
    return txs, [_payment("1303500", date(2026, 10, 19))]


def test_astrid_case_matches_eleven_and_misses_three() -> None:
    txs, payments = _astrid_records()

    result = match_lines(_astrid_lines(), txs, payments, RECONCILE_WINDOW_DAYS)

    assert len(result.matched) == 11
    assert {line.description for line in result.missing} == _MISSING
    assert any(m.line.kind == StatementLineKind.CARD_PAYMENT for m in result.matched)


def test_identical_lines_consume_one_record_each() -> None:
    lines = [_line("Flypass", "5700", date(2026, 10, 26)) for _ in range(3)]
    txs = [_tx("Flypass", "5700", date(2026, 10, 26))]

    result = match_lines(lines, txs, [], RECONCILE_WINDOW_DAYS)

    assert (len(result.matched), len(result.missing)) == (1, 2)


def test_window_is_three_days_inclusive() -> None:
    line = [_line("Flypass", "5700", date(2026, 10, 20))]

    within = match_lines(line, [_tx("Flypass", "5700", date(2026, 10, 23))], [], 3)
    outside = match_lines(line, [_tx("Flypass", "5700", date(2026, 10, 24))], [], 3)

    assert len(within.matched) == 1
    assert len(outside.matched) == 0 and len(outside.missing) == 1


def test_matches_transaction_date_never_budget_date() -> None:
    line = [_line("Flypass", "5700", date(2026, 10, 20))]
    # Credit charge: budget_date lands weeks later on the card's payment date.
    tx = _tx("Flypass", "5700", date(2026, 10, 1), budget_date=date(2026, 10, 20))

    assert match_lines(line, [tx], [], RECONCILE_WINDOW_DAYS).matched == []


def test_amount_must_be_exactly_equal() -> None:
    line = [_line("Flypass", "5700", date(2026, 10, 20))]

    result = match_lines(line, [_tx("Flypass", "5701", date(2026, 10, 20))], [], 3)

    assert result.matched == []


def test_income_transaction_never_matches_an_expense_line() -> None:
    line = [_line("Abono", "50000", date(2026, 10, 20))]
    income = _tx("Abono", "50000", date(2026, 10, 20), TransactionType.INCOME, None)

    assert match_lines(line, [income], [], RECONCILE_WINDOW_DAYS).matched == []


def test_income_line_matches_income_transaction() -> None:
    line = [_line("Nomina", "3000000", date(2026, 10, 20), StatementLineKind.INCOME, None)]
    income = _tx("Nomina", "3000000", date(2026, 10, 21), TransactionType.INCOME, None)

    assert len(match_lines(line, [income], [], RECONCILE_WINDOW_DAYS).matched) == 1


def test_expense_never_matches_a_card_payment_line() -> None:
    line = [
        _line("Gracias por tu pago", "1303500", date(2026, 10, 19), StatementLineKind.CARD_PAYMENT)
    ]
    expense = _tx("Gracias por tu pago", "1303500", date(2026, 10, 19))

    assert match_lines(line, [expense], [], RECONCILE_WINDOW_DAYS).matched == []


def test_expense_line_never_consumes_a_card_payment_row() -> None:
    # An expense LINE of the same amount must not consume the card payment row.
    line = [_line("Algo", "1303500", date(2026, 10, 19))]

    result = match_lines(line, [], [_payment("1303500", date(2026, 10, 19))], 3)

    assert result.matched == []


def test_closest_day_wins_the_one_to_one_assignment() -> None:
    near = _line("Flypass", "5700", date(2026, 10, 20))
    far = _line("Flypass", "5700", date(2026, 10, 23))
    tx = _tx("Flypass", "5700", date(2026, 10, 23))

    result = match_lines([near, far], [tx], [], RECONCILE_WINDOW_DAYS)

    assert [m.line.date for m in result.matched] == [date(2026, 10, 23)]
    assert result.missing == [near]


def test_same_card_payment_wins_a_tie() -> None:
    line = [
        _line("Gracias por tu pago", "100000", date(2026, 10, 19), StatementLineKind.CARD_PAYMENT)
    ]
    payments = [
        _payment("100000", date(2026, 10, 19), card="Falabella"),
        _payment("100000", date(2026, 10, 19), card="Nu"),
    ]

    result = match_lines(line, [], payments, RECONCILE_WINDOW_DAYS)

    assert result.matched[0].matched_label == "Nu"


def test_equal_amount_on_another_card_still_matches() -> None:
    line = [
        _line("Gracias por tu pago", "100000", date(2026, 10, 19), StatementLineKind.CARD_PAYMENT)
    ]

    result = match_lines(line, [], [_payment("100000", date(2026, 10, 19), card="Falabella")], 3)

    assert len(result.matched) == 1


def test_similar_name_wins_a_tie_before_card() -> None:
    line = [_line("Flypass", "5700", date(2026, 10, 20))]
    txs = [
        _tx("Peaje", "5700", date(2026, 10, 20)),
        _tx("Flypass", "5700", date(2026, 10, 20)),
    ]

    result = match_lines(line, txs, [], RECONCILE_WINDOW_DAYS)

    assert result.matched[0].matched_label == "Flypass"


def test_credit_transaction_wins_the_card_tie_for_a_card_line() -> None:
    line = [_line("Compra", "5700", date(2026, 10, 20), card="Nu")]
    txs = [
        _tx("Tienda", "5700", date(2026, 10, 20), payment_method=PaymentMethod.EFECTIVO),
        _tx("Tienda", "5700", date(2026, 10, 20), payment_method=PaymentMethod.CREDITO),
    ]

    result = match_lines(line, txs, [], RECONCILE_WINDOW_DAYS)

    assert result.matched[0].matched_label == "Tienda"
    assert len(result.missing) == 0


def test_no_records_means_everything_is_missing() -> None:
    lines = _astrid_lines()

    result = match_lines(lines, [], [], RECONCILE_WINDOW_DAYS)

    assert result.matched == [] and result.missing == lines


def test_everything_registered_leaves_nothing_missing() -> None:
    txs, payments = _astrid_records()
    txs += [_tx(d, a, date(2026, 10, day)) for d, a, day in _CHARGES if d in _MISSING]

    result = match_lines(_astrid_lines(), txs, payments, RECONCILE_WINDOW_DAYS)

    assert result.missing == [] and len(result.matched) == 14


# --- StatementReconciler (fetching service) ---------------------------------


class _StubTransactions:
    def __init__(self, items: list[Transaction]) -> None:
        self._items = items
        self.calls: list[dict[str, Any]] = []

    async def list_by_period(
        self, user_id: str, *, period_start: date, period_end: date, **kwargs: Any
    ) -> list[Transaction]:
        self.calls.append({"start": period_start, "end": period_end, **kwargs})
        return self._items


class _StubCards:
    def __init__(self, payments: list[CardPaymentView]) -> None:
        self._payments = payments
        self.calls: list[tuple[date, date]] = []

    async def list_payments(
        self, user_id: str, period_start: date, period_end: date
    ) -> list[CardPaymentView]:
        self.calls.append((period_start, period_end))
        return self._payments


def _reconciler(
    txs: _StubTransactions, cards: _StubCards
) -> StatementReconciler:
    return StatementReconciler(
        cast(TransactionServiceABC, txs), cast(CreditCardServiceABC, cards)
    )


async def test_reconcile_makes_two_queries_over_the_padded_range() -> None:
    records, payments = _astrid_records()
    txs, cards = _StubTransactions(records), _StubCards(payments)

    result = await _reconciler(txs, cards).reconcile(USER, _astrid_lines())

    assert len(txs.calls) == 1 and len(cards.calls) == 1
    # Oct 19..26 padded by the 3-day window.
    assert (txs.calls[0]["start"], txs.calls[0]["end"]) == (date(2026, 10, 16), date(2026, 10, 29))
    assert cards.calls == [(date(2026, 10, 16), date(2026, 10, 29))]
    assert txs.calls[0]["date_field"] == "transaction_date"
    assert len(result.matched) == 11 and len(result.missing) == 3


async def test_reconcile_with_no_lines_runs_no_queries() -> None:
    txs, cards = _StubTransactions([]), _StubCards([])

    result = await _reconciler(txs, cards).reconcile(USER, [])

    assert result.matched == [] and result.missing == []
    assert txs.calls == [] and cards.calls == []


def test_undated_line_is_never_matched_even_with_a_recent_equal_record() -> None:
    line = [_line("Compra", "5000", None)]
    txs = [_tx("Compra", "5000", date(2026, 10, 30))]

    result = match_lines(line, txs, [], RECONCILE_WINDOW_DAYS)

    assert result.matched == [] and result.missing == line


async def test_reconcile_skips_queries_when_no_line_has_a_date() -> None:
    txs, cards = _StubTransactions([]), _StubCards([])
    lines = [_line("Compra", "5000", None)]

    result = await _reconciler(txs, cards).reconcile(USER, lines)

    assert result.missing == lines
    assert txs.calls == [] and cards.calls == []


def test_a_greedy_choice_never_strands_a_line_with_a_free_record() -> None:
    # The Oct 10 line prefers the Oct 10 record, but the Oct 7 line can ONLY take that
    # one (Oct 13 is 6 days away): the Oct 10 line must move to the Oct 13 record.
    lines = [_line("Uber", "12000", date(2026, 10, 10)), _line("Uber", "12000", date(2026, 10, 7))]
    txs = [_tx("Uber", "12000", date(2026, 10, 10)), _tx("Uber", "12000", date(2026, 10, 13))]

    result = match_lines(lines, txs, [], RECONCILE_WINDOW_DAYS)

    assert len(result.matched) == 2 and result.missing == []
    by_line = {m.line.date: m.matched_date for m in result.matched}
    assert by_line == {
        date(2026, 10, 7): date(2026, 10, 10),
        date(2026, 10, 10): date(2026, 10, 13),
    }
