"""Unit tests for the credit-card toolkit (service mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.agents.tools.card_tools import CARD_TOOL_SCHEMAS, CardToolkit
from app.core.exceptions import DatabaseQueryError
from app.shared.clock import bound_today
from app.shared.turn import TurnContext, bound_turn
from app.shared.types import CardId, UserId
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.cards.models import (
    CardPayment,
    CardPaymentCreate,
    CardPaymentView,
    CreditCard,
    CreditCardCreate,
    CreditCardStatus,
)
from app.src.cards.services.schedule_change_service import CardScheduleChangeService
from app.src.pending.models import PendingAction
from app.src.pending.services.pending_action_service import PendingActionService
from tests.fakes import FakePendingActionRepository

pytestmark = pytest.mark.asyncio


def _toolkit(service: CreditCardServiceABC) -> CardToolkit:
    """Toolkit wired with the REAL schedule service over an in-memory pending store."""
    pending = PendingActionService(FakePendingActionRepository())
    return CardToolkit(service, CardScheduleChangeService(service, pending))


def _turn(turn_id: str, conversation_id: str = "conv-1") -> TurnContext:
    return TurnContext(turn_id=turn_id, conversation_id=conversation_id)


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


def _status(card: CreditCard, *, historical: bool = False) -> CreditCardStatus:
    """Card 15/5 as of Jul 3: the May 16-Jun 15 statement is due Jul 5.

    A historical (selected-month) status carries no statement figures.
    """
    return CreditCardStatus(
        card=card,
        cycle_start=date(2026, 6, 16),
        cycle_end=date(2026, 7, 15),
        spent_cycle=Decimal("200000"),
        balance=Decimal("500000"),
        available=Decimal("4500000"),
        utilization=10.0,
        next_payment_date=date(2026, 7, 5),
        cycle_payment_date=date(2026, 8, 5),
        statement_start=None if historical else date(2026, 5, 16),
        statement_end=None if historical else date(2026, 6, 15),
        statement_amount=None if historical else Decimal("300000"),
    )


class FakeCardService(CreditCardServiceABC):
    def __init__(self, cards: list[CreditCard] | None = None) -> None:
        self.created: list[CreditCardCreate] = []
        self.payments: list[tuple[str, Decimal]] = []
        self._cards = cards if cards is not None else [_card()]

    async def create_card(self, card: CreditCardCreate, user_id: UserId) -> CreditCard:
        self.created.append(card)
        return _card(card.name)

    async def list_cards(self, user_id: UserId) -> list[CreditCard]:
        return self._cards

    async def get_all_status(
        self, user_id: UserId, as_of: date | None = None, **kwargs: object
    ) -> list[CreditCardStatus]:
        return [_status(c) for c in self._cards]

    async def get_status(
        self, card_id: CardId, user_id: UserId, as_of: date | None = None
    ) -> CreditCardStatus:
        return _status(self._cards[0])

    async def total_paid_up_to(self, user_id: UserId, as_of: date) -> Decimal:
        return Decimal("0")

    async def register_payment(
        self, card_id: CardId, user_id: UserId, payment: CardPaymentCreate
    ) -> CardPayment:
        self.payments.append((card_id, payment.amount))
        self.last_payment_date = payment.payment_date
        return CardPayment(
            id="pay-1",
            user_id=user_id,
            card_id=card_id,
            amount=payment.amount,
            payment_date=payment.payment_date,
            created_at=datetime(2026, 7, 3, tzinfo=UTC),
        )

    async def resolve_by_name(self, name: str, user_id: UserId) -> CreditCard | None:
        target = name.lower()
        return next((c for c in self._cards if target in c.name.lower()), None)

    async def list_payments(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[CardPaymentView]:
        return []

    async def remove_payment(
        self,
        user_id: UserId,
        amount: Decimal,
        *,
        payment_date: date | None = None,
        card_id: CardId | None = None,
    ) -> CardPayment | None:
        self.removed_payment: tuple[Decimal, date | None, CardId | None] = (
            amount,
            payment_date,
            card_id,
        )
        return CardPayment(
            id="pay-1",
            user_id=user_id,
            card_id=card_id or "card-1",
            amount=amount,
            payment_date=payment_date or date(2026, 7, 1),
            created_at=datetime(2026, 7, 3, tzinfo=UTC),
        )

    async def update_card(
        self,
        card_id: CardId,
        user_id: UserId,
        *,
        name: str | None = None,
        credit_limit: Decimal | None = None,
        cutoff_day: int | None = None,
        payment_day: int | None = None,
    ) -> CreditCard:
        self.updated: dict[str, object] = {
            "name": name,
            "credit_limit": credit_limit,
            "cutoff_day": cutoff_day,
            "payment_day": payment_day,
        }
        updated = self._cards[0].model_copy(
            update={k: v for k, v in self.updated.items() if v is not None}
        )
        self._cards[0] = updated
        return updated

    async def delete_card(self, card_id: CardId, user_id: UserId) -> CreditCard:
        self.deleted: str = card_id
        return self._cards[0].model_copy(update={"is_active": False})


async def test_create_card() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch(
        "create_card",
        {"name": "Visa BBVA", "credit_limit": 5000000, "cutoff_day": 15, "payment_day": 5},
        "u1",
    )
    assert service.created[0].name == "Visa BBVA"
    assert service.created[0].cutoff_day == 15
    assert "Visa BBVA" in result


async def test_create_card_invalid_days() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch(
        "create_card",
        {"name": "X", "credit_limit": 100, "cutoff_day": 40, "payment_day": 5},
        "u1",
    )
    assert not service.created
    assert "no pude" in result.lower()


async def test_query_cards_shows_balance_and_available() -> None:
    result = await _toolkit(FakeCardService()).dispatch("query_cards", {}, "u1")
    assert "Visa BBVA" in result
    assert "500000" in result and "4500000" in result
    assert "En el ciclo abierto" in result


async def test_query_cards_live_separates_amount_due_from_open_cycle() -> None:
    result = await _toolkit(FakeCardService()).dispatch("query_cards", {}, "u1")

    assert "corte día 15, pago día 5" in result
    # Total debt is labeled as TOTAL, never as what's due on the next date.
    assert "deuda TOTAL $500000" in result
    assert "A pagar el 2026-07-05: $300000 (corte 2026-05-16–2026-06-15)" in result
    assert "En el ciclo abierto 2026-06-16–2026-07-15 (se paga el 2026-08-05): $200000" in result
    assert "Vencido" not in result


async def test_query_cards_open_cycle_due_shows_overdue_debt() -> None:
    # The next due date is the open cycle's (its amount isn't final yet); unpaid
    # debt whose due date passed must still surface, never "nothing due".
    open_status = _status(_card()).model_copy(
        update={
            "next_payment_date": date(2026, 8, 5),
            "statement_start": date(2026, 6, 16),
            "statement_end": date(2026, 7, 15),
            "statement_amount": None,
            "overdue_amount": Decimal("150000"),
        }
    )

    class OpenCycleService(FakeCardService):
        async def get_all_status(
            self, user_id: UserId, as_of: date | None = None, **kwargs: object
        ) -> list[CreditCardStatus]:
            return [open_status]

    result = await _toolkit(OpenCycleService()).dispatch("query_cards", {}, "u1")

    assert "A pagar el 2026-08-05: monto aún no definido" in result
    assert "Vencido sin pagar (de cortes anteriores ya vencidos): $150000" in result


async def test_query_cards_paid_statement_says_covered() -> None:
    covered = _status(_card()).model_copy(update={"statement_amount": Decimal("0")})

    class CoveredService(FakeCardService):
        async def get_all_status(
            self, user_id: UserId, as_of: date | None = None, **kwargs: object
        ) -> list[CreditCardStatus]:
            return [covered]

    result = await _toolkit(CoveredService()).dispatch("query_cards", {}, "u1")

    assert "A pagar el 2026-07-05: $0 (ya cubierto)" in result


class RecordingCardService(FakeCardService):
    """Records the period window the toolkit asks the service for."""

    def __init__(self, cards: list[CreditCard] | None = None) -> None:
        super().__init__(cards)
        self.windows: list[tuple[date | None, date | None]] = []

    async def get_all_status(
        self,
        user_id: UserId,
        as_of: date | None = None,
        *,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> list[CreditCardStatus]:
        self.windows.append((period_start, period_end))
        return [_status(c, historical=period_start is not None) for c in self._cards]


async def test_query_cards_without_period_asks_for_the_current_cycle() -> None:
    service = RecordingCardService()
    await _toolkit(service).dispatch("query_cards", {}, "u1")
    assert service.windows == [(None, None)]


async def test_query_cards_with_a_month_scopes_the_spend_to_it() -> None:
    service = RecordingCardService()

    with bound_today(date(2026, 8, 4)):
        result = await _toolkit(service).dispatch(
            "query_cards", {"period": "mes_pasado"}, "u1"
        )

    # The window is the whole previous calendar month, resolved server-side.
    assert service.windows == [(date(2026, 7, 1), date(2026, 7, 31))]
    assert "gastado en el mes pasado" in result
    assert "cierre de ese periodo" in result
    assert "corte día 15, pago día 5" in result
    # A month spans two statements: no due date or amount is claimed.
    assert "A pagar" not in result
    assert "próximo pago" not in result
    assert "2026-07-05" not in result


async def test_query_cards_accepts_a_specific_month_and_all_history() -> None:
    service = RecordingCardService()
    await _toolkit(service).dispatch("query_cards", {"period": "2026-06"}, "u1")
    with bound_today(date(2026, 8, 4)):
        await _toolkit(service).dispatch("query_cards", {"period": "todo"}, "u1")

    assert service.windows[0] == (date(2026, 6, 1), date(2026, 6, 30))
    assert service.windows[1] == (date(1970, 1, 1), date(2026, 8, 31))


async def test_query_cards_rejects_an_unknown_period() -> None:
    service = RecordingCardService()

    result = await _toolkit(service).dispatch(
        "query_cards", {"period": "junio"}, "u1"
    )

    # Never silently answers for the current month instead.
    assert not service.windows
    assert "de qué periodo" in result.lower()


async def test_query_cards_with_no_cards_in_a_period() -> None:
    service = RecordingCardService(cards=[])
    result = await _toolkit(service).dispatch(
        "query_cards", {"period": "2026-06"}, "u1"
    )
    assert result == "No tienes tarjetas registradas."


async def test_pay_card_resolves_by_name() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch(
        "pay_card", {"card_name": "visa", "amount": 300000}, "u1"
    )
    assert service.payments[0] == ("card-1", Decimal("300000"))
    assert "300000" in result


async def test_pay_card_honors_stated_date() -> None:
    # "pagué el 1 de julio" must store that date, not today.
    service = FakeCardService()
    await _toolkit(service).dispatch(
        "pay_card",
        {"card_name": "visa", "amount": 300000, "payment_date": "2026-07-01"},
        "u1",
    )
    assert service.last_payment_date == date(2026, 7, 1)


async def test_pay_unknown_card_returns_message() -> None:
    service = FakeCardService(cards=[_card(name="Mastercard")])
    result = await _toolkit(service).dispatch(
        "pay_card", {"card_name": "Amex", "amount": 100}, "u1"
    )
    assert not service.payments
    assert "no encontré" in result.lower()


async def test_update_card_changes_limit() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch(
        "update_card", {"card_name": "visa", "new_credit_limit": 8000000}, "u1"
    )
    assert service.updated["credit_limit"] == Decimal("8000000")
    assert "8000000" in result


async def test_update_card_limit_only_has_no_frozen_charges_note() -> None:
    result = await _toolkit(FakeCardService()).dispatch(
        "update_card", {"card_name": "visa", "new_credit_limit": 8000000}, "u1"
    )
    assert "cupo: $5000000 → $8000000" in result
    assert "cargos ya registrados" not in result
    assert "PROPUESTA" not in result


async def test_update_card_name_change_uses_new_name_in_heading() -> None:
    result = await _toolkit(FakeCardService()).dispatch(
        "update_card", {"card_name": "visa", "new_name": "Visa Oro"}, "u1"
    )
    assert "tarjeta Visa Oro:" in result
    assert "nombre: Visa BBVA → Visa Oro" in result
    assert "cargos ya registrados" not in result


async def test_update_card_cutoff_only_proposes_and_does_not_change_the_card() -> None:
    service = FakeCardService()
    with bound_turn(_turn("t1")):
        result = await _toolkit(service).dispatch(
            "update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1"
        )
    assert not hasattr(service, "updated")
    assert service._cards[0].cutoff_day == 15
    assert result.startswith("PROPUESTA (aún NO aplicada): Visa BBVA: corte 15 → 20")
    assert "el día de pago sigue el 5" in result
    assert "confirm_card_change" in result
    assert "✏️" not in result


async def test_update_card_payment_day_only_proposes() -> None:
    service = FakeCardService()
    with bound_turn(_turn("t1")):
        result = await _toolkit(service).dispatch(
            "update_card", {"card_name": "visa", "new_payment_day": 10}, "u1"
        )
    assert not hasattr(service, "updated")
    assert "pago 5 → 10" in result
    assert "el día de corte sigue el 15" in result


async def test_update_card_limit_and_cutoff_applies_limit_and_only_proposes_cutoff() -> None:
    service = FakeCardService()
    with bound_turn(_turn("t1")):
        result = await _toolkit(service).dispatch(
            "update_card",
            {"card_name": "visa", "new_cutoff_day": 20, "new_credit_limit": 8000000},
            "u1",
        )
    assert service.updated["credit_limit"] == Decimal("8000000")
    assert service.updated["cutoff_day"] is None
    assert service._cards[0].cutoff_day == 15
    assert "✏️ Actualicé tu tarjeta Visa BBVA: cupo: $5000000 → $8000000." in result
    assert "PROPUESTA (aún NO aplicada)" in result
    assert "cargos ya registrados" not in result


async def test_update_card_same_days_say_no_changes() -> None:
    with bound_turn(_turn("t1")):
        result = await _toolkit(FakeCardService()).dispatch(
            "update_card", {"card_name": "visa", "new_cutoff_day": 15}, "u1"
        )
    assert "ya tenía esos datos" in result
    assert "→" not in result
    assert "PROPUESTA" not in result


async def test_update_card_ignores_invalid_day() -> None:
    service = FakeCardService()
    await _toolkit(service).dispatch(
        "update_card",
        {"card_name": "visa", "new_name": "Visa Oro", "new_cutoff_day": 40},
        "u1",
    )
    # Out-of-range day is dropped; the valid field still goes through.
    assert service.updated["cutoff_day"] is None
    assert service.updated["name"] == "Visa Oro"


async def test_update_card_no_fields_asks() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch("update_card", {"card_name": "visa"}, "u1")
    assert not hasattr(service, "updated")
    assert "¿qué quieres cambiar" in result.lower()


async def test_update_unknown_card_returns_message() -> None:
    service = FakeCardService(cards=[_card(name="Mastercard")])
    result = await _toolkit(service).dispatch(
        "update_card", {"card_name": "Amex", "new_credit_limit": 100}, "u1"
    )
    assert not hasattr(service, "updated")
    assert "no encontré" in result.lower()


async def test_propose_without_a_bound_turn_fails_closed() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch(
        "update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1"
    )
    assert "no se cambió nada" in result
    assert not hasattr(service, "updated")
    assert service._cards[0].cutoff_day == 15


async def test_confirm_without_a_bound_turn_fails_closed() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch("confirm_card_change", {}, "u1")
    assert "no se cambió nada" in result
    assert not hasattr(service, "updated")


async def test_confirm_in_a_later_turn_applies_the_proposal_once() -> None:
    service = FakeCardService()
    toolkit = _toolkit(service)
    with bound_turn(_turn("t1")):
        await toolkit.dispatch("update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1")
    with bound_turn(_turn("t2")):
        result = await toolkit.dispatch("confirm_card_change", {}, "u1")
        again = await toolkit.dispatch("confirm_card_change", {}, "u1")

    assert "✏️ Actualicé tu tarjeta Visa BBVA: corte: día 15 → 20." in result
    assert "pago:" not in result
    assert "cargos ya registrados" in result
    assert service._cards[0].cutoff_day == 20
    assert "No hay un cambio de corte/pago aceptado" in again


async def test_confirm_in_the_same_turn_has_no_effect() -> None:
    service = FakeCardService()
    toolkit = _toolkit(service)
    with bound_turn(_turn("t1")):
        await toolkit.dispatch("update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1")
        result = await toolkit.dispatch("confirm_card_change", {}, "u1")
    assert "No hay un cambio de corte/pago aceptado por el usuario" in result
    assert "Vuelve a proponerlo con update_card" in result
    assert service._cards[0].cutoff_day == 15
    assert not hasattr(service, "updated")


async def test_confirm_reports_stale_when_the_days_changed_since_the_proposal() -> None:
    service = FakeCardService()
    toolkit = _toolkit(service)
    with bound_turn(_turn("t1")):
        await toolkit.dispatch("update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1")
    service._cards[0] = service._cards[0].model_copy(update={"cutoff_day": 7})
    with bound_turn(_turn("t2")):
        result = await toolkit.dispatch("confirm_card_change", {}, "u1")
    assert result == "Los días de la tarjeta cambiaron desde la propuesta; vuelve a proponer."
    assert service._cards[0].cutoff_day == 7


async def test_proposal_and_confirmation_never_expose_internal_ids() -> None:
    service = FakeCardService()
    toolkit = _toolkit(service)
    with bound_turn(_turn("turn-secret", "conv-secret")):
        proposal = await toolkit.dispatch(
            "update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1"
        )
    with bound_turn(_turn("turn-2", "conv-secret")):
        applied = await toolkit.dispatch("confirm_card_change", {}, "u1")
    for text in (proposal, applied):
        for hidden in ("card-1", "u1", "turn-", "conv-secret"):
            assert hidden not in text


async def test_storage_failure_while_proposing_is_reported_not_raised() -> None:
    class BrokenRepo(FakePendingActionRepository):
        async def upsert(self, action: PendingAction) -> None:
            raise DatabaseQueryError("upsert", "db down")

    service = FakeCardService()
    toolkit = CardToolkit(
        service, CardScheduleChangeService(service, PendingActionService(BrokenRepo()))
    )
    with bound_turn(_turn("t1")):
        result = await toolkit.dispatch(
            "update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1"
        )
    assert "no se cambió nada" in result
    assert service._cards[0].cutoff_day == 15


def test_confirm_card_change_schema_takes_no_arguments() -> None:
    schema = next(s for s in CARD_TOOL_SCHEMAS if s["function"]["name"] == "confirm_card_change")
    assert schema["function"]["parameters"] == {"type": "object", "properties": {}}


async def test_remove_card_payment_resolves_and_deletes() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch(
        "remove_card_payment", {"card_name": "visa", "amount": 300000}, "u1"
    )
    assert service.removed_payment == (Decimal("300000"), None, "card-1")
    assert "borré" in result.lower()
    assert "300000" in result


async def test_remove_card_payment_no_card_filter() -> None:
    # Without a card name it removes by amount across cards (card_id None).
    service = FakeCardService()
    await _toolkit(service).dispatch(
        "remove_card_payment", {"amount": 500000, "payment_date": "2026-07-01"}, "u1"
    )
    assert service.removed_payment == (Decimal("500000"), date(2026, 7, 1), None)


async def test_remove_card_payment_invalid_amount() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch(
        "remove_card_payment", {"amount": 0}, "u1"
    )
    assert not hasattr(service, "removed_payment")
    assert "mayor a 0" in result.lower()


async def test_remove_card_payment_unknown_card() -> None:
    service = FakeCardService(cards=[_card(name="Mastercard")])
    result = await _toolkit(service).dispatch(
        "remove_card_payment", {"card_name": "Amex", "amount": 100}, "u1"
    )
    assert not hasattr(service, "removed_payment")
    assert "no encontré" in result.lower()


async def test_delete_card_soft_deletes() -> None:
    service = FakeCardService()
    result = await _toolkit(service).dispatch("delete_card", {"card_name": "visa"}, "u1")
    assert service.deleted == "card-1"
    assert "eliminé" in result.lower()


async def test_delete_unknown_card_returns_message() -> None:
    service = FakeCardService(cards=[_card(name="Mastercard")])
    result = await _toolkit(service).dispatch("delete_card", {"card_name": "Amex"}, "u1")
    assert not hasattr(service, "deleted")
    assert "no encontré" in result.lower()


async def test_update_card_again_in_the_confirming_turn_keeps_the_proposal() -> None:
    service = FakeCardService()
    toolkit = _toolkit(service)
    with bound_turn(_turn("t1")):
        await toolkit.dispatch("update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1")
    with bound_turn(_turn("t2")):
        again = await toolkit.dispatch(
            "update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1"
        )
        applied = await toolkit.dispatch("confirm_card_change", {}, "u1")

    assert again.startswith("Ya está propuesto: Visa BBVA: corte 15 → 20")
    assert "confirm_card_change" in again
    assert "✏️ Actualicé tu tarjeta Visa BBVA: corte: día 15 → 20." in applied
    assert service._cards[0].cutoff_day == 20


async def test_a_different_update_card_in_the_next_turn_needs_another_turn() -> None:
    service = FakeCardService()
    toolkit = _toolkit(service)
    with bound_turn(_turn("t1")):
        await toolkit.dispatch("update_card", {"card_name": "visa", "new_cutoff_day": 20}, "u1")
    with bound_turn(_turn("t2")):
        other = await toolkit.dispatch(
            "update_card", {"card_name": "visa", "new_cutoff_day": 25}, "u1"
        )
        same_turn = await toolkit.dispatch("confirm_card_change", {}, "u1")
    with bound_turn(_turn("t3")):
        later = await toolkit.dispatch("confirm_card_change", {}, "u1")

    assert other.startswith("PROPUESTA (aún NO aplicada)")
    assert "No hay un cambio de corte/pago aceptado" in same_turn
    assert "corte: día 15 → 25" in later


async def test_failed_proposal_after_a_direct_change_uses_a_schedule_specific_text() -> None:
    class BrokenRepo(FakePendingActionRepository):
        async def get(self, user_id: str, conversation_id: str) -> PendingAction | None:
            raise DatabaseQueryError("select", "db down")

    service = FakeCardService()
    toolkit = CardToolkit(
        service, CardScheduleChangeService(service, PendingActionService(BrokenRepo()))
    )
    with bound_turn(_turn("t1")):
        result = await toolkit.dispatch(
            "update_card",
            {"card_name": "visa", "new_cutoff_day": 20, "new_credit_limit": 8000000},
            "u1",
        )

    assert "✏️ Actualicé tu tarjeta Visa BBVA: cupo:" in result
    assert "El cambio de corte/pago no se guardó; inténtalo de nuevo." in result
    assert "no se cambió nada" not in result
