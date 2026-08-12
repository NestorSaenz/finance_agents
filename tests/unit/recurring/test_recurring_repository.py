"""Unit tests for the Supabase recurring repository (DB mocked)."""

from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import RecurringNotFoundError
from app.shared.interfaces.database import QueryResult
from app.shared.types import PaymentMethod, TransactionType
from app.src.recurring.models import RecurringCreate, RecurringFrequency
from app.src.recurring.repositories.recurring_repository import RecurringRepository
from tests.fakes import FakeDatabase, make_recurring_row


def _new_recurring() -> RecurringCreate:
    return RecurringCreate(
        amount=Decimal("50000"),
        description="Netflix",
        transaction_type=TransactionType.EXPENSE,
        category="suscripciones",
        day_of_month=5,
        next_run_date=date(2026, 6, 5),
    )


class TestCreate:
    async def test_persists_and_maps(self) -> None:
        db = FakeDatabase()
        repo = RecurringRepository(db)

        result = await repo.create(_new_recurring(), "u1")

        inserted = db.inserted[0]
        assert inserted["type"] == "expense"  # mapped from transaction_type
        assert inserted["amount"] == "50000"  # Decimal serialized as string
        assert inserted["next_run_date"] == "2026-06-05"
        assert inserted["frequency"] == "monthly"
        assert inserted["active"] is True
        assert result.transaction_type == TransactionType.EXPENSE
        assert result.amount == Decimal("50000")

    async def test_persists_credit_payment_method(self) -> None:
        db = FakeDatabase()
        repo = RecurringRepository(db)
        rec = RecurringCreate(
            amount=Decimal("100"),
            description="Spotify",
            transaction_type=TransactionType.EXPENSE,
            payment_method=PaymentMethod.CREDITO,
            card_id="card-1",
            day_of_month=3,
        )

        await repo.create(rec, "u1")

        inserted = db.inserted[0]
        assert inserted["payment_method"] == "credito"
        assert inserted["card_id"] == "card-1"


class TestListDue:
    async def test_returns_only_active_on_or_before_as_of(self) -> None:
        rows = [
            make_recurring_row(id="due-active", next_run_date="2026-06-05", active=True),
            make_recurring_row(id="future", next_run_date="2026-12-01", active=True),
            make_recurring_row(id="due-paused", next_run_date="2026-06-05", active=False),
        ]
        repo = RecurringRepository(FakeDatabase(rows=rows))

        due = await repo.list_due(date(2026, 6, 20))

        ids = {r.id for r in due}
        assert ids == {"due-active"}

    async def test_maps_frequency(self) -> None:
        rows = [make_recurring_row(next_run_date="2026-06-05")]
        repo = RecurringRepository(FakeDatabase(rows=rows))

        due = await repo.list_due(date(2026, 6, 20))

        assert due[0].frequency == RecurringFrequency.MONTHLY


class TestUpdate:
    async def test_update_applies_and_maps(self) -> None:
        db = FakeDatabase(rows=[make_recurring_row()])
        repo = RecurringRepository(db)

        await repo.update("rec-1", "u1", {"active": False})

        data, filters = db.updated[-1]
        assert data == {"active": False}
        assert filters == {"id": "rec-1", "user_id": "u1"}

    async def test_update_missing_raises(self) -> None:
        class NoRowDB(FakeDatabase):
            async def update(self, table, data, filters):  # type: ignore[no-untyped-def]
                return QueryResult(data=[], count=0)

        repo = RecurringRepository(NoRowDB())

        with pytest.raises(RecurringNotFoundError):
            await repo.update("missing", "u1", {"active": False})


class TestDelete:
    async def test_delete_scoped_by_user(self) -> None:
        db = FakeDatabase(rows=[make_recurring_row()])
        repo = RecurringRepository(db)

        await repo.delete("rec-1", "u1")

        assert db.deleted[-1] == {"id": "rec-1", "user_id": "u1"}
