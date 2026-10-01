"""Unit tests for the credit-card service (balance, cycle, payments)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.exceptions import CardNotFoundError
from app.shared.types import CardId, UserId
from app.src.cards.interfaces import (
    CardPaymentRepositoryABC,
    CreditCardRepositoryABC,
    CreditCardSpendingABC,
)
from app.src.cards.models import (
    CardPayment,
    CardPaymentCreate,
    CreditCard,
    CreditCardCreate,
)
from app.src.cards.services.credit_card_service import CreditCardService

REF = date(2026, 7, 3)


def _card(name: str = "Visa BBVA", cutoff_day: int = 15, payment_day: int = 5) -> CreditCard:
    return CreditCard(
        id="card-1",
        user_id="u1",
        name=name,
        credit_limit=Decimal("5000000"),
        cutoff_day=cutoff_day,
        payment_day=payment_day,
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeCardRepo(CreditCardRepositoryABC):
    def __init__(self, cards: list[CreditCard] | None = None) -> None:
        self.cards = cards if cards is not None else [_card()]

    async def create(self, card: CreditCardCreate, user_id: UserId) -> CreditCard:
        return _card(card.name)

    async def get_by_id(self, card_id: CardId, user_id: UserId) -> CreditCard | None:
        return next((c for c in self.cards if c.id == card_id), None)

    async def list_active(self, user_id: UserId) -> list[CreditCard]:
        return [c for c in self.cards if c.is_active]

    async def update(
        self,
        card_id: CardId,
        user_id: UserId,
        *,
        name: str | None = None,
        credit_limit: Decimal | None = None,
        cutoff_day: int | None = None,
        payment_day: int | None = None,
    ) -> CreditCard | None:
        card = next((c for c in self.cards if c.id == card_id), None)
        if card is None:
            return None
        updated = card.model_copy(
            update={
                k: v
                for k, v in {
                    "name": name,
                    "credit_limit": credit_limit,
                    "cutoff_day": cutoff_day,
                    "payment_day": payment_day,
                }.items()
                if v is not None
            }
        )
        self.cards = [updated if c.id == card_id else c for c in self.cards]
        return updated

    async def deactivate(self, card_id: CardId, user_id: UserId) -> CreditCard | None:
        card = next((c for c in self.cards if c.id == card_id), None)
        if card is None:
            return None
        deactivated = card.model_copy(update={"is_active": False})
        self.cards = [deactivated if c.id == card_id else c for c in self.cards]
        return deactivated


class FakePaymentRepo(CardPaymentRepositoryABC):
    def __init__(
        self,
        total: Decimal = Decimal("0"),
        dated: list[tuple[date, Decimal]] | None = None,
        payments: list[CardPayment] | None = None,
    ) -> None:
        self.total = total
        self.dated = dated  # (payment_date, amount) pairs to honor `as_of`
        self.created: list[tuple[str, Decimal]] = []
        self.payments = payments or []  # full rows for list_in_period / delete
        self.deleted: list[str] = []

    async def create(
        self, payment: CardPaymentCreate, card_id: CardId, user_id: UserId
    ) -> CardPayment:
        self.created.append((card_id, payment.amount))
        return CardPayment(
            id="pay-1",
            user_id=user_id,
            card_id=card_id,
            amount=payment.amount,
            payment_date=payment.payment_date,
            created_at=datetime(2026, 7, 3, tzinfo=UTC),
        )

    async def total_paid(
        self, user_id: UserId, card_id: CardId, as_of: date | None = None
    ) -> Decimal:
        if self.dated is None:
            return self.total
        return sum(
            (amt for d, amt in self.dated if as_of is None or d <= as_of),
            Decimal("0"),
        )

    async def total_paid_up_to(self, user_id: UserId, as_of: date) -> Decimal:
        if self.dated is None:
            return self.total
        return sum((amt for d, amt in self.dated if d <= as_of), Decimal("0"))

    async def list_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPayment]:
        return [
            p for p in self.payments if period_start <= p.payment_date <= period_end
        ]

    async def delete(self, payment_id: str, user_id: UserId) -> None:
        self.deleted.append(payment_id)


class FakeSpending(CreditCardSpendingABC):
    def __init__(
        self, cycle: Decimal, total: Decimal, period: Decimal | None = None
    ) -> None:
        self.cycle = cycle
        self.total = total
        self.period = period  # the selected-month total when a period is requested

    async def charges_summary(
        self,
        user_id: UserId,
        card_id: CardId,
        cycle_start: date,
        as_of: date,
        period: tuple[date, date] | None = None,
    ) -> tuple[Decimal, Decimal, Decimal]:
        period_total = self.period if self.period is not None else Decimal("0")
        return self.total, self.cycle, period_total


@pytest.mark.asyncio
async def test_status_computes_balance_and_available() -> None:
    # charged total 800k, paid 300k -> balance 500k; limit 5M -> available 4.5M
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(total=Decimal("300000")),
        FakeSpending(cycle=Decimal("200000"), total=Decimal("800000")),
    )

    statuses = await service.get_all_status("u1", as_of=REF)

    assert len(statuses) == 1
    s = statuses[0]
    assert s.balance == Decimal("500000")
    assert s.available == Decimal("4500000")
    assert s.spent_cycle == Decimal("200000")
    assert s.cycle_start == date(2026, 6, 16)
    assert s.cycle_end == date(2026, 7, 15)
    # On Jul 3 the May 16-Jun 15 statement (closed Jun 15) is still due Jul 5; the
    # open cycle's Aug 5 comes after it.
    assert s.next_payment_date == date(2026, 7, 5)
    assert s.cycle_payment_date == date(2026, 8, 5)
    assert (s.statement_start, s.statement_end) == (date(2026, 5, 16), date(2026, 6, 15))
    # Due Jul 5 = total debt minus the open cycle's charges: 500k - 200k.
    assert s.statement_amount == Decimal("300000")
    assert s.overdue_amount is None


@pytest.mark.asyncio
async def test_available_never_exceeds_limit_when_overpaid() -> None:
    # Paid more than charged -> negative balance (credit in favor); available must
    # be capped at the limit, never limit + overpayment.
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(total=Decimal("1000000")),
        FakeSpending(cycle=Decimal("0"), total=Decimal("300000")),
    )

    s = (await service.get_all_status("u1", as_of=REF))[0]

    assert s.balance == Decimal("-700000")  # overpaid
    assert s.available == Decimal("5000000")  # capped at the limit, not 5.7M


@pytest.mark.asyncio
async def test_spent_reflects_selected_period() -> None:
    # With a period, 'spent' comes from the selected-month total in charges_summary,
    # not the current cycle.
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(total=Decimal("0")),
        FakeSpending(cycle=Decimal("200000"), total=Decimal("800000"), period=Decimal("588770")),
    )

    s = (
        await service.get_all_status(
            "u1", as_of=REF, period_start=date(2026, 6, 1), period_end=date(2026, 6, 30)
        )
    )[0]

    assert s.spent_cycle == Decimal("588770")  # the June figure, not the cycle's 200k


@pytest.mark.asyncio
async def test_historical_balance_excludes_later_payments() -> None:
    # Viewing June: charges up to June-end are 588,770; a payment made in AUGUST
    # must NOT reduce June's balance (reconstructed at the month-end, not today).
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(dated=[(date(2026, 8, 8), Decimal("1645349"))]),
        FakeSpending(cycle=Decimal("0"), total=Decimal("588770"), period=Decimal("588770")),
    )

    s = (
        await service.get_all_status(
            "u1", period_start=date(2026, 6, 1), period_end=date(2026, 6, 30)
        )
    )[0]

    assert s.balance == Decimal("588770")  # August abono excluded at June month-end
    assert s.available == Decimal("5000000") - Decimal("588770")


@pytest.mark.asyncio
async def test_current_month_stays_live_not_month_end() -> None:
    # The CURRENT month's period_end is in the future (end of month). The cycle and
    # next payment must be computed at TODAY, not month-end (which would jump a cycle).
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(total=Decimal("0")),
        FakeSpending(cycle=Decimal("200000"), total=Decimal("800000"), period=Decimal("200000")),
    )

    s = (
        await service.get_all_status(
            "u1",
            as_of=REF,  # 2026-07-03
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),  # future relative to REF
        )
    )[0]

    # cutoff 15 -> cycle at Jul 3 is Jun16–Jul15, next payment Jul 5. Evaluated at
    # month-end (Jul 31) it would be the Jul16–Aug15 cycle and Aug 5 instead.
    assert s.cycle_start == date(2026, 6, 16)
    assert s.cycle_end == date(2026, 7, 15)
    assert s.next_payment_date == date(2026, 7, 5)


@pytest.mark.asyncio
async def test_astrid_rappi_regression_pays_closed_statement_first() -> None:
    # Real report: Rappi cutoff 19 / pay 2, asked on Sep 30. The Aug 20-Sep 19
    # statement is due Oct 2 — Safi wrongly said "next payment Nov 2, nothing due".
    service = CreditCardService(
        FakeCardRepo(cards=[_card("Rappi", cutoff_day=19, payment_day=2)]),
        FakePaymentRepo(total=Decimal("2000000")),
        FakeSpending(cycle=Decimal("1500000"), total=Decimal("12573212")),
    )

    s = (await service.get_all_status("u1", as_of=date(2026, 9, 30)))[0]

    assert s.balance == Decimal("10573212")  # TOTAL debt, open cycle included
    assert s.next_payment_date == date(2026, 10, 2)
    assert (s.statement_start, s.statement_end) == (date(2026, 8, 20), date(2026, 9, 19))
    # Due Oct 2 = total debt minus the open (Sep 20-Oct 19) cycle's charges.
    assert s.statement_amount == Decimal("10573212") - Decimal("1500000")
    assert (s.cycle_start, s.cycle_end) == (date(2026, 9, 20), date(2026, 10, 19))
    assert s.cycle_payment_date == date(2026, 11, 2)


@pytest.mark.asyncio
async def test_payment_day_after_cutoff_day_bbva() -> None:
    # BBVA cutoff 10 / pay 26: on Sep 15 the Aug 11-Sep 10 statement is due Sep 26.
    service = CreditCardService(
        FakeCardRepo(cards=[_card("BBVA", cutoff_day=10, payment_day=26)]),
        FakePaymentRepo(total=Decimal("0")),
        FakeSpending(cycle=Decimal("100000"), total=Decimal("900000")),
    )

    s = (await service.get_all_status("u1", as_of=date(2026, 9, 15)))[0]

    assert s.next_payment_date == date(2026, 9, 26)
    assert (s.statement_start, s.statement_end) == (date(2026, 8, 11), date(2026, 9, 10))
    assert s.statement_amount == Decimal("800000")
    assert s.cycle_payment_date == date(2026, 10, 26)


@pytest.mark.asyncio
async def test_open_cycle_due_date_surfaces_overdue_debt() -> None:
    # BBVA on Sep 28: Sep 26 passed, so the next due date (Oct 26) belongs to the
    # still-open Sep 11-Oct 10 cycle — its amount isn't final. Unpaid debt from
    # before the cycle (its due date passed) must surface as overdue, never as
    # "nothing due".
    service = CreditCardService(
        FakeCardRepo(cards=[_card("BBVA", cutoff_day=10, payment_day=26)]),
        FakePaymentRepo(total=Decimal("300000")),
        FakeSpending(cycle=Decimal("100000"), total=Decimal("900000")),
    )

    s = (await service.get_all_status("u1", as_of=date(2026, 9, 28)))[0]

    assert s.next_payment_date == date(2026, 10, 26)
    assert (s.statement_start, s.statement_end) == (date(2026, 9, 11), date(2026, 10, 10))
    assert s.statement_amount is None  # the statement hasn't closed yet
    assert s.overdue_amount == Decimal("500000")  # 600k debt - 100k open cycle


@pytest.mark.asyncio
async def test_statement_amount_never_negative_when_overpaid() -> None:
    # Paid more than everything charged before the open cycle: nothing is due (0),
    # not a negative amount.
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(total=Decimal("700000")),
        FakeSpending(cycle=Decimal("200000"), total=Decimal("800000")),
    )

    s = (await service.get_all_status("u1", as_of=REF))[0]

    assert s.balance == Decimal("100000")
    assert s.statement_amount == Decimal("0")


@pytest.mark.asyncio
async def test_historical_view_claims_no_statement() -> None:
    # A selected month spans two statements: no due date/amount is claimed.
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(total=Decimal("0")),
        FakeSpending(cycle=Decimal("0"), total=Decimal("588770"), period=Decimal("588770")),
    )

    s = (
        await service.get_all_status(
            "u1", as_of=REF, period_start=date(2026, 6, 1), period_end=date(2026, 6, 30)
        )
    )[0]

    assert s.statement_start is None
    assert s.statement_end is None
    assert s.statement_amount is None
    assert s.overdue_amount is None


@pytest.mark.asyncio
async def test_past_month_shows_the_payment_date_inside_that_month() -> None:
    # Viewing June (payment_day 5): the "fecha de pago" is June 5 — the payment
    # that falls in the viewed month — not the live next payment (Jul 5 / Aug 5).
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(total=Decimal("0")),
        FakeSpending(cycle=Decimal("0"), total=Decimal("588770"), period=Decimal("588770")),
    )

    s = (
        await service.get_all_status(
            "u1", as_of=REF, period_start=date(2026, 6, 1), period_end=date(2026, 6, 30)
        )
    )[0]

    assert s.next_payment_date == date(2026, 6, 5)


@pytest.mark.asyncio
async def test_current_month_period_still_claims_the_statement() -> None:
    # The dashboard sends a period even for "este_mes". It includes today, so the
    # view is LIVE: the due date and the amount due must be reported.
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(total=Decimal("0")),
        FakeSpending(cycle=Decimal("200000"), total=Decimal("800000"), period=Decimal("200000")),
    )

    s = (
        await service.get_all_status(
            "u1",
            as_of=REF,  # 2026-07-03, cutoff 15 / payment 5
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),
        )
    )[0]

    assert s.next_payment_date == date(2026, 7, 5)
    assert s.statement_amount == Decimal("600000")  # 800k debt - 200k open cycle


@pytest.mark.asyncio
async def test_period_ending_today_is_still_live() -> None:
    # The month's last day is today: the month isn't over, so it's the live view
    # (statement figures claimed), not a past-month reconstruction.
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(total=Decimal("0")),
        FakeSpending(cycle=Decimal("0"), total=Decimal("100000"), period=Decimal("100000")),
    )

    s = (
        await service.get_all_status(
            "u1",
            as_of=date(2026, 7, 31),
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),
        )
    )[0]

    assert s.statement_start is not None


@pytest.mark.asyncio
async def test_total_paid_up_to_sums_only_payments_on_or_before_as_of() -> None:
    # Cumulative across all cards: a July payment counts at July-end, an August one
    # does not. The service delegates straight to the payment repo.
    service = CreditCardService(
        FakeCardRepo(),
        FakePaymentRepo(
            dated=[(date(2026, 7, 10), Decimal("100000")), (date(2026, 8, 2), Decimal("50000"))]
        ),
        FakeSpending(Decimal("0"), Decimal("0")),
    )

    assert await service.total_paid_up_to("u1", date(2026, 7, 31)) == Decimal("100000")
    assert await service.total_paid_up_to("u1", date(2026, 8, 31)) == Decimal("150000")


@pytest.mark.asyncio
async def test_register_payment_persists() -> None:
    payments = FakePaymentRepo()
    service = CreditCardService(
        FakeCardRepo(), payments, FakeSpending(Decimal("0"), Decimal("0"))
    )

    await service.register_payment(
        "card-1", "u1", CardPaymentCreate(amount=Decimal("100000"), payment_date=REF)
    )

    assert payments.created[0] == ("card-1", Decimal("100000"))


@pytest.mark.asyncio
async def test_register_payment_unknown_card_raises() -> None:
    service = CreditCardService(
        FakeCardRepo(cards=[]), FakePaymentRepo(), FakeSpending(Decimal("0"), Decimal("0"))
    )

    with pytest.raises(CardNotFoundError):
        await service.register_payment(
            "missing", "u1", CardPaymentCreate(amount=Decimal("10"), payment_date=REF)
        )


@pytest.mark.asyncio
async def test_resolve_by_name_is_fuzzy() -> None:
    service = CreditCardService(
        FakeCardRepo(cards=[_card(name="Visa BBVA")]),
        FakePaymentRepo(),
        FakeSpending(Decimal("0"), Decimal("0")),
    )

    card = await service.resolve_by_name("visa", "u1")

    assert card is not None and card.id == "card-1"


@pytest.mark.asyncio
async def test_resolve_by_name_tolerates_typos() -> None:
    service = CreditCardService(
        FakeCardRepo(cards=[_card(name="rappid"), _card(name="falabella")]),
        FakePaymentRepo(),
        FakeSpending(Decimal("0"), Decimal("0")),
    )

    # "rapid" (missing a p) is not a substring of "rappid" but is clearly it.
    matched = await service.resolve_by_name("rapid", "u1")
    assert matched is not None and matched.name == "rappid"

    # An unrelated word must not fuzzy-match any card.
    assert await service.resolve_by_name("pizza", "u1") is None


@pytest.mark.asyncio
async def test_update_card_changes_limit_and_name() -> None:
    service = CreditCardService(
        FakeCardRepo(), FakePaymentRepo(), FakeSpending(Decimal("0"), Decimal("0"))
    )

    updated = await service.update_card(
        "card-1", "u1", name="Visa Oro", credit_limit=Decimal("8000000")
    )

    assert updated.name == "Visa Oro"
    assert updated.credit_limit == Decimal("8000000")
    assert updated.cutoff_day == 15  # unchanged


@pytest.mark.asyncio
async def test_update_card_unknown_raises() -> None:
    service = CreditCardService(
        FakeCardRepo(cards=[]), FakePaymentRepo(), FakeSpending(Decimal("0"), Decimal("0"))
    )

    with pytest.raises(CardNotFoundError):
        await service.update_card("missing", "u1", name="X")


@pytest.mark.asyncio
async def test_delete_card_soft_deletes_and_hides_it() -> None:
    repo = FakeCardRepo()
    service = CreditCardService(repo, FakePaymentRepo(), FakeSpending(Decimal("0"), Decimal("0")))

    deleted = await service.delete_card("card-1", "u1")

    assert deleted.is_active is False
    assert await repo.list_active("u1") == []  # no longer listed


@pytest.mark.asyncio
async def test_delete_card_unknown_raises() -> None:
    service = CreditCardService(
        FakeCardRepo(cards=[]), FakePaymentRepo(), FakeSpending(Decimal("0"), Decimal("0"))
    )

    with pytest.raises(CardNotFoundError):
        await service.delete_card("missing", "u1")


def _payment(pid: str, amount: str, on: date, card_id: str = "card-1") -> CardPayment:
    return CardPayment(
        id=pid,
        user_id="u1",
        card_id=card_id,
        amount=Decimal(amount),
        payment_date=on,
        created_at=datetime(2026, 7, 3, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_list_payments_carries_card_id_and_name() -> None:
    # The view must expose card_id (for precise per-card association) plus the name.
    payments = FakePaymentRepo(payments=[_payment("p1", "100000", date(2026, 7, 3))])
    service = CreditCardService(FakeCardRepo(), payments, FakeSpending(Decimal("0"), Decimal("0")))

    views = await service.list_payments("u1", date(2026, 7, 1), date(2026, 7, 31))

    assert len(views) == 1
    assert views[0].card_id == "card-1"
    assert views[0].card_name == "Visa BBVA"
    assert views[0].amount == Decimal("100000")


@pytest.mark.asyncio
async def test_remove_payment_matches_and_deletes() -> None:
    payments = FakePaymentRepo(payments=[_payment("p1", "300000", date(2026, 7, 1))])
    service = CreditCardService(FakeCardRepo(), payments, FakeSpending(Decimal("0"), Decimal("0")))

    removed = await service.remove_payment("u1", Decimal("300000"))

    assert removed is not None
    assert removed.id == "p1"
    assert payments.deleted == ["p1"]


@pytest.mark.asyncio
async def test_remove_payment_scopes_by_card_and_date() -> None:
    payments = FakePaymentRepo(
        payments=[
            _payment("p1", "500000", date(2026, 7, 1), card_id="card-1"),
            _payment("p2", "500000", date(2026, 7, 1), card_id="card-2"),
        ]
    )
    service = CreditCardService(FakeCardRepo(), payments, FakeSpending(Decimal("0"), Decimal("0")))

    removed = await service.remove_payment(
        "u1", Decimal("500000"), payment_date=date(2026, 7, 1), card_id="card-2"
    )

    assert removed is not None and removed.id == "p2"
    assert payments.deleted == ["p2"]


@pytest.mark.asyncio
async def test_remove_payment_no_match_returns_none() -> None:
    payments = FakePaymentRepo(payments=[_payment("p1", "300000", date(2026, 7, 1))])
    service = CreditCardService(FakeCardRepo(), payments, FakeSpending(Decimal("0"), Decimal("0")))

    removed = await service.remove_payment("u1", Decimal("999999"))

    assert removed is None
    assert payments.deleted == []
