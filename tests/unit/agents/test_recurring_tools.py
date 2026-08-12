"""Unit tests for the recurring toolkit (service mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.agents.tools.recurring_tools import (
    CREATE_RECURRING_TOOL,
    DELETE_RECURRING_TOOL,
    LIST_RECURRING_TOOL,
    PAUSE_RECURRING_TOOL,
    RESUME_RECURRING_TOOL,
    UPDATE_RECURRING_TOOL,
    RecurringToolkit,
)
from app.shared.types import PaymentMethod, TransactionType, UserId
from app.src.recurring.interfaces import RecurringServiceABC
from app.src.recurring.models import (
    RecurringCreate,
    RecurringFrequency,
    RecurringTransaction,
    RecurringUpdate,
)
from tests.unit.agents.test_card_tools import FakeCardService, _card


def _rec(
    *,
    rec_id: str = "rec-1",
    description: str = "Netflix",
    amount: Decimal = Decimal("50000"),
    day_of_month: int = 5,
    active: bool = True,
    card_id: str | None = None,
    payment_method: PaymentMethod | None = None,
) -> RecurringTransaction:
    return RecurringTransaction(
        id=rec_id,
        user_id="u1",
        amount=amount,
        description=description,
        transaction_type=TransactionType.EXPENSE,
        category="suscripciones",
        payment_method=payment_method,
        card_id=card_id,
        frequency=RecurringFrequency.MONTHLY,
        day_of_month=day_of_month,
        next_run_date=date(2026, 6, 5),
        last_run_date=None,
        active=active,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class FakeRecurringService(RecurringServiceABC):
    def __init__(self, existing: RecurringTransaction | None = None) -> None:
        self.created: list[tuple[RecurringCreate, str]] = []
        self.updated: list[tuple[str, str, RecurringUpdate]] = []
        self.deleted: list[tuple[str, str]] = []
        self.set_active_calls: list[tuple[str, str, bool]] = []
        self._existing = existing
        self.listed: list[RecurringTransaction] = [existing] if existing else []
        # When set, find_matches returns these (drives the disambiguation test).
        self.matches: list[RecurringTransaction] | None = None

    async def create_recurring(
        self, rec: RecurringCreate, user_id: UserId
    ) -> RecurringTransaction:
        self.created.append((rec, user_id))
        return _rec(
            description=rec.description,
            amount=rec.amount,
            day_of_month=rec.day_of_month,
            card_id=rec.card_id,
            payment_method=rec.payment_method,
        )

    async def list_recurring(self, user_id: UserId) -> list[RecurringTransaction]:
        return self.listed

    async def update_recurring(
        self, recurring_id: str, user_id: UserId, data: RecurringUpdate
    ) -> RecurringTransaction:
        self.updated.append((recurring_id, user_id, data))
        assert self._existing is not None
        patch = data.model_dump(exclude_none=True)
        return self._existing.model_copy(update=patch)

    async def delete_recurring(
        self, recurring_id: str, user_id: UserId
    ) -> RecurringTransaction:
        self.deleted.append((recurring_id, user_id))
        assert self._existing is not None
        return self._existing

    async def set_active(
        self, recurring_id: str, user_id: UserId, active: bool
    ) -> RecurringTransaction:
        self.set_active_calls.append((recurring_id, user_id, active))
        assert self._existing is not None
        return self._existing.model_copy(update={"active": active})

    async def resolve_by_name(
        self, name: str, user_id: UserId
    ) -> RecurringTransaction | None:
        matches = await self.find_matches(name, user_id)
        return matches[0] if matches else None

    async def find_matches(
        self, name: str, user_id: UserId
    ) -> list[RecurringTransaction]:
        return list(self.matches) if self.matches is not None else self._default_matches(name)

    def _default_matches(self, name: str) -> list[RecurringTransaction]:
        if self._existing is None:
            return []
        return (
            [self._existing]
            if name.lower() in self._existing.description.lower()
            else []
        )

    async def run_due(self, as_of: date) -> int:
        return 0


class TestCreate:
    async def test_create_dispatch(self) -> None:
        service = FakeRecurringService()
        result = await RecurringToolkit(service).dispatch(
            CREATE_RECURRING_TOOL,
            {
                "amount": 50000,
                "description": "Netflix",
                "transaction_type": "expense",
                "day_of_month": 5,
            },
            "u1",
        )
        rec, uid = service.created[0]
        assert rec.description == "Netflix"
        assert rec.day_of_month == 5
        assert uid == "u1"
        assert "Netflix" in result

    async def test_create_ignores_user_id_from_model(self) -> None:
        # Security: user_id comes from the auth context, never from the model args.
        service = FakeRecurringService()
        await RecurringToolkit(service).dispatch(
            CREATE_RECURRING_TOOL,
            {
                "user_id": "attacker",
                "amount": 100,
                "description": "Rent",
                "transaction_type": "expense",
                "day_of_month": 1,
            },
            "real-user",
        )
        _rec_in, uid = service.created[0]
        assert uid == "real-user"

    async def test_create_invalid_day_returns_message(self) -> None:
        service = FakeRecurringService()
        result = await RecurringToolkit(service).dispatch(
            CREATE_RECURRING_TOOL,
            {
                "amount": 100,
                "description": "X",
                "transaction_type": "expense",
                "day_of_month": 40,
            },
            "u1",
        )
        assert service.created == []
        assert "día" in result.lower()

    async def test_create_credit_resolves_card_by_name(self) -> None:
        service = FakeRecurringService()
        cards = FakeCardService(cards=[_card("Visa BBVA")])
        result = await RecurringToolkit(service, cards=cards).dispatch(
            CREATE_RECURRING_TOOL,
            {
                "amount": 200,
                "description": "Spotify",
                "transaction_type": "expense",
                "day_of_month": 3,
                "payment_method": "credito",
                "card_name": "BBVA",
            },
            "u1",
        )
        rec, _uid = service.created[0]
        assert rec.card_id == "card-1"
        assert rec.payment_method == PaymentMethod.CREDITO
        assert "Spotify" in result

    async def test_create_credit_unknown_card_asks(self) -> None:
        service = FakeRecurringService()
        cards = FakeCardService(cards=[_card("Visa BBVA")])
        result = await RecurringToolkit(service, cards=cards).dispatch(
            CREATE_RECURRING_TOOL,
            {
                "amount": 200,
                "description": "Spotify",
                "transaction_type": "expense",
                "day_of_month": 3,
                "payment_method": "credito",
                "card_name": "Nu",
            },
            "u1",
        )
        assert service.created == []  # not created without a resolvable card
        assert "tarjeta" in result.lower()


class TestListUpdateDelete:
    async def test_list_dispatch(self) -> None:
        service = FakeRecurringService(existing=_rec())
        result = await RecurringToolkit(service).dispatch(
            LIST_RECURRING_TOOL, {}, "u1"
        )
        assert "Netflix" in result
        assert "activo" in result

    async def test_list_empty(self) -> None:
        result = await RecurringToolkit(FakeRecurringService()).dispatch(
            LIST_RECURRING_TOOL, {}, "u1"
        )
        assert "No tienes" in result

    async def test_update_resolves_by_description(self) -> None:
        service = FakeRecurringService(existing=_rec())
        result = await RecurringToolkit(service).dispatch(
            UPDATE_RECURRING_TOOL,
            {"description": "Netflix", "new_amount": 60000},
            "u1",
        )
        rid, _uid, data = service.updated[0]
        assert rid == "rec-1"
        assert data.amount == Decimal("60000")
        assert "Actualicé" in result

    async def test_update_unknown_returns_not_found(self) -> None:
        service = FakeRecurringService(existing=_rec())
        result = await RecurringToolkit(service).dispatch(
            UPDATE_RECURRING_TOOL,
            {"description": "Spotify", "new_amount": 1},
            "u1",
        )
        assert service.updated == []
        assert "No encontré" in result

    async def test_delete_resolves_by_description(self) -> None:
        service = FakeRecurringService(existing=_rec())
        result = await RecurringToolkit(service).dispatch(
            DELETE_RECURRING_TOOL, {"description": "Netflix"}, "u1"
        )
        assert service.deleted == [("rec-1", "u1")]
        assert "Eliminé" in result


class TestPauseResume:
    async def test_pause_dispatch(self) -> None:
        service = FakeRecurringService(existing=_rec())
        result = await RecurringToolkit(service).dispatch(
            PAUSE_RECURRING_TOOL, {"description": "Netflix"}, "u1"
        )
        assert service.set_active_calls == [("rec-1", "u1", False)]
        assert "Pausé" in result

    async def test_resume_dispatch(self) -> None:
        service = FakeRecurringService(existing=_rec(active=False))
        result = await RecurringToolkit(service).dispatch(
            RESUME_RECURRING_TOOL, {"description": "Netflix"}, "u1"
        )
        assert service.set_active_calls == [("rec-1", "u1", True)]
        assert "Reanudé" in result

    async def test_pause_unknown_returns_not_found(self) -> None:
        service = FakeRecurringService(existing=_rec())
        result = await RecurringToolkit(service).dispatch(
            PAUSE_RECURRING_TOOL, {"description": "Spotify"}, "u1"
        )
        assert service.set_active_calls == []
        assert "No encontré" in result


class TestDisambiguation:
    def _ambiguous_service(self) -> FakeRecurringService:
        service = FakeRecurringService(existing=_rec(description="Netflix"))
        service.matches = [
            _rec(rec_id="a", description="Netflix"),
            _rec(rec_id="b", description="Netflix Premium"),
        ]
        return service

    async def test_delete_asks_which_when_multiple_match(self) -> None:
        service = self._ambiguous_service()
        result = await RecurringToolkit(service).dispatch(
            DELETE_RECURRING_TOOL, {"description": "Netflix"}, "u1"
        )
        assert service.deleted == []  # never silently picks one
        assert "varios" in result.lower()
        assert "Netflix Premium" in result

    async def test_pause_asks_which_when_multiple_match(self) -> None:
        service = self._ambiguous_service()
        result = await RecurringToolkit(service).dispatch(
            PAUSE_RECURRING_TOOL, {"description": "Netflix"}, "u1"
        )
        assert service.set_active_calls == []
        assert "varios" in result.lower()

    async def test_update_asks_which_when_multiple_match(self) -> None:
        service = self._ambiguous_service()
        result = await RecurringToolkit(service).dispatch(
            UPDATE_RECURRING_TOOL,
            {"description": "Netflix", "new_amount": 1},
            "u1",
        )
        assert service.updated == []
        assert "varios" in result.lower()


class TestUpdateCompleteness:
    async def test_rename(self) -> None:
        service = FakeRecurringService(existing=_rec())
        await RecurringToolkit(service).dispatch(
            UPDATE_RECURRING_TOOL,
            {"description": "Netflix", "new_description": "Netflix Familiar"},
            "u1",
        )
        _rid, _uid, data = service.updated[0]
        assert data.description == "Netflix Familiar"

    async def test_change_type(self) -> None:
        service = FakeRecurringService(existing=_rec())
        await RecurringToolkit(service).dispatch(
            UPDATE_RECURRING_TOOL,
            {"description": "Netflix", "new_type": "income"},
            "u1",
        )
        _rid, _uid, data = service.updated[0]
        assert data.transaction_type == TransactionType.INCOME

    async def test_switch_to_efectivo_passes_cash_method(self) -> None:
        service = FakeRecurringService(existing=_rec(card_id="card-1"))
        await RecurringToolkit(service).dispatch(
            UPDATE_RECURRING_TOOL,
            {"description": "Netflix", "payment_method": "efectivo"},
            "u1",
        )
        _rid, _uid, data = service.updated[0]
        assert data.payment_method == PaymentMethod.EFECTIVO
        # The service clears card_id on efectivo; the tool need not send a card.
        assert data.card_id is None

    async def test_switch_to_credito_links_resolved_card(self) -> None:
        service = FakeRecurringService(existing=_rec())
        cards = FakeCardService(cards=[_card("Visa BBVA")])
        await RecurringToolkit(service, cards=cards).dispatch(
            UPDATE_RECURRING_TOOL,
            {"description": "Netflix", "payment_method": "credito", "card_name": "BBVA"},
            "u1",
        )
        _rid, _uid, data = service.updated[0]
        assert data.payment_method == PaymentMethod.CREDITO
        assert data.card_id == "card-1"

    async def test_switch_to_credito_unknown_card_asks(self) -> None:
        service = FakeRecurringService(existing=_rec())
        cards = FakeCardService(cards=[_card("Visa BBVA")])
        result = await RecurringToolkit(service, cards=cards).dispatch(
            UPDATE_RECURRING_TOOL,
            {"description": "Netflix", "payment_method": "credito", "card_name": "Nu"},
            "u1",
        )
        assert service.updated == []  # not updated without a resolvable card
        assert "tarjeta" in result.lower()

    async def test_unlink_card(self) -> None:
        service = FakeRecurringService(existing=_rec(card_id="card-1"))
        await RecurringToolkit(service).dispatch(
            UPDATE_RECURRING_TOOL,
            {"description": "Netflix", "unlink_card": True},
            "u1",
        )
        _rid, _uid, data = service.updated[0]
        assert data.clear_card is True
