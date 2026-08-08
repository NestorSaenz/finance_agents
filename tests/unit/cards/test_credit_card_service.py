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


def _card(name: str = "Visa BBVA") -> CreditCard:
    return CreditCard(
        id="card-1",
        user_id="u1",
        name=name,
        credit_limit=Decimal("5000000"),
        cutoff_day=15,
        payment_day=5,
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
    ) -> None:
        self.total = total
        self.dated = dated  # (payment_date, amount) pairs to honor `as_of`
        self.created: list[tuple[str, Decimal]] = []

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

    async def list_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPayment]:
        return []


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
    assert s.next_payment_date == date(2026, 8, 5)


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

    # cutoff 15 -> cycle at Jul 3 is Jun16–Jul15, next payment Aug 5 (NOT Sep 5).
    assert s.cycle_start == date(2026, 6, 16)
    assert s.cycle_end == date(2026, 7, 15)
    assert s.next_payment_date == date(2026, 8, 5)


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
