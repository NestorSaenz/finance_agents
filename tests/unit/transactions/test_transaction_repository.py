"""Unit tests for the Supabase transaction repository (DB mocked)."""

from datetime import date
from decimal import Decimal

import pytest

from app.shared.types import CategoryType, TransactionType
from app.src.transactions.models import TransactionCreate
from app.src.transactions.repositories.transaction_repository import TransactionRepository
from tests.fakes import FakeDatabase, make_transaction_row


def _new_transaction(category: CategoryType | None = CategoryType.RESTAURANTES) -> TransactionCreate:
    return TransactionCreate(
        amount=Decimal("50000"),
        description="Almuerzo con colegas",
        transaction_type=TransactionType.EXPENSE,
        transaction_date=date(2024, 12, 20),
        category=category,
    )


class TestCreate:
    async def test_persists_and_maps_row(self) -> None:
        db = FakeDatabase()
        repo = TransactionRepository(db)

        result = await repo.create(_new_transaction(), user_id="u1")

        # The row was inserted with the expected, serializable shape.
        inserted = db.inserted[0]
        assert inserted["user_id"] == "u1"
        assert inserted["amount"] == "50000"  # Decimal -> str (exact numeric)
        assert inserted["type"] == "expense"
        assert inserted["category"] == "restaurantes"
        assert inserted["transaction_date"] == "2024-12-20"
        # The returned domain object is mapped back correctly.
        assert result.amount == Decimal("50000.0")
        assert result.category == CategoryType.RESTAURANTES
        assert result.transaction_date == date(2024, 12, 20)

    async def test_missing_category_defaults_to_otros_at_persistence(self) -> None:
        db = FakeDatabase()
        repo = TransactionRepository(db)

        await repo.create(_new_transaction(category=None), user_id="u1")

        assert db.inserted[0]["category"] == "otros"

    async def test_empty_insert_response_raises(self) -> None:
        class EmptyDB(FakeDatabase):
            async def insert(self, table: str, data: object) -> object:
                from app.shared.interfaces.database import QueryResult

                return QueryResult(data=[], count=0)

        repo = TransactionRepository(EmptyDB())
        with pytest.raises(Exception) as exc_info:
            await repo.create(_new_transaction(), user_id="u1")
        assert "TRANSACTION_INSERT_FAILED" in str(exc_info.value.__dict__.get("code", ""))


class TestGetById:
    async def test_returns_none_when_missing(self) -> None:
        repo = TransactionRepository(FakeDatabase(rows=[]))
        assert await repo.get_by_id("tx-1", "u1") is None

    async def test_maps_existing_row(self) -> None:
        repo = TransactionRepository(FakeDatabase(rows=[make_transaction_row()]))
        tx = await repo.get_by_id("tx-1", "u1")
        assert tx is not None
        assert tx.id == "tx-1"
        assert tx.transaction_type == TransactionType.EXPENSE


class TestListAndCount:
    async def test_list_applies_pagination_and_filters(self) -> None:
        rows = [make_transaction_row(id=f"tx-{i}") for i in range(3)]
        db = FakeDatabase(rows=rows)
        repo = TransactionRepository(db)

        items = await repo.list_page(
            "u1", limit=20, offset=0, transaction_type=TransactionType.EXPENSE
        )

        assert len(items) == 3
        config = db.select_configs[-1]
        assert config.limit == 20
        assert config.filters == {"user_id": "u1", "type": "expense"}
        assert config.order_by == "created_at"
        assert config.order_ascending is False

    async def test_count_returns_number_of_rows(self) -> None:
        rows = [make_transaction_row(id=f"tx-{i}") for i in range(5)]
        repo = TransactionRepository(FakeDatabase(rows=rows))
        assert await repo.count("u1") == 5

    async def test_custom_category_is_preserved(self) -> None:
        # A user-defined (non-enum) category is kept as stored, not flattened.
        repo = TransactionRepository(
            FakeDatabase(rows=[make_transaction_row(category="jardineria")])
        )
        tx = await repo.get_by_id("tx-1", "u1")
        assert tx is not None
        assert tx.category == "jardineria"

    async def test_null_category_falls_back_to_otros(self) -> None:
        repo = TransactionRepository(
            FakeDatabase(rows=[make_transaction_row(category=None)])
        )
        tx = await repo.get_by_id("tx-1", "u1")
        assert tx is not None
        assert tx.category == CategoryType.OTROS.value


class TestUpdateAndDelete:
    async def test_update_sends_data_and_user_scoped_filter(self) -> None:
        db = FakeDatabase(rows=[make_transaction_row()])
        repo = TransactionRepository(db)

        tx = await repo.update("tx-1", "u1", {"amount": "75"})

        data, filters = db.updated[0]
        assert data == {"amount": "75"}
        assert filters == {"id": "tx-1", "user_id": "u1"}  # scoped to the owner
        assert tx.id == "tx-1"

    async def test_delete_is_scoped_by_user(self) -> None:
        db = FakeDatabase(rows=[make_transaction_row()])
        repo = TransactionRepository(db)

        await repo.delete("tx-1", "u1")

        assert db.deleted[0] == {"id": "tx-1", "user_id": "u1"}
