"""Unit tests for the transaction service (repository + categorizer mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.exceptions import TransactionNotFoundError
from app.shared.types import CategoryType, CurrencyType, TransactionType
from app.src.transactions.interfaces import (
    TransactionCategorizerABC,
    TransactionRepositoryABC,
)
from app.src.transactions.models import Transaction, TransactionCreate
from app.src.transactions.services.transaction_service import TransactionService


class FakeCategorizer(TransactionCategorizerABC):
    def __init__(self, category: CategoryType = CategoryType.RESTAURANTES) -> None:
        self.category = category
        self.called_with: list[str] = []

    async def categorize(self, description: str) -> CategoryType:
        self.called_with.append(description)
        return self.category


class FakeRepository(TransactionRepositoryABC):
    def __init__(self, stored: Transaction | None = None, total: int = 0) -> None:
        self.created: list[TransactionCreate] = []
        self.stored = stored
        self.total = total
        self.list_kwargs: dict = {}
        self.updated: list[tuple[str, dict]] = []
        self.deleted: list[str] = []

    async def create(self, transaction: TransactionCreate, user_id: str) -> Transaction:
        self.created.append(transaction)
        return Transaction(
            id="tx-1",
            user_id=user_id,
            amount=transaction.amount,
            currency=transaction.currency,
            transaction_type=transaction.transaction_type,
            description=transaction.description,
            category=transaction.category or CategoryType.OTROS,
            transaction_date=transaction.transaction_date,
            source=transaction.source,
            created_at=datetime.now(UTC),
        )

    async def get_by_id(self, transaction_id: str, user_id: str) -> Transaction | None:
        return self.stored

    async def list_page(self, user_id: str, **kwargs: object) -> list[Transaction]:
        self.list_kwargs = kwargs
        return [self.stored] if self.stored else []

    async def count(self, user_id: str, **kwargs: object) -> int:
        return self.total

    async def update(self, transaction_id: str, user_id: str, data: dict[str, object]) -> Transaction:
        self.updated.append((transaction_id, data))
        assert self.stored is not None
        return self.stored

    async def delete(self, transaction_id: str, user_id: str) -> None:
        self.deleted.append(transaction_id)


def _new_transaction(category: CategoryType | None) -> TransactionCreate:
    return TransactionCreate(
        amount=Decimal("100"),
        description="Cena en restaurante",
        transaction_type=TransactionType.EXPENSE,
        transaction_date=date(2024, 12, 20),
        category=category,
    )


class TestCreateTransaction:
    async def test_auto_categorizes_when_category_missing(self) -> None:
        repo = FakeRepository()
        categorizer = FakeCategorizer(CategoryType.RESTAURANTES)
        service = TransactionService(repo, categorizer)

        result = await service.create_transaction(_new_transaction(None), "u1")

        assert categorizer.called_with == ["Cena en restaurante"]
        assert repo.created[0].category == CategoryType.RESTAURANTES
        assert result.category == CategoryType.RESTAURANTES

    async def test_keeps_explicit_category_and_skips_categorizer(self) -> None:
        repo = FakeRepository()
        categorizer = FakeCategorizer()
        service = TransactionService(repo, categorizer)

        await service.create_transaction(_new_transaction(CategoryType.VIAJES), "u1")

        assert categorizer.called_with == []
        assert repo.created[0].category == CategoryType.VIAJES


class TestGetTransaction:
    async def test_raises_when_not_found(self) -> None:
        service = TransactionService(FakeRepository(stored=None), FakeCategorizer())
        with pytest.raises(TransactionNotFoundError):
            await service.get_transaction("missing", "u1")


def _stored_tx() -> Transaction:
    return Transaction(
        id="tx-1",
        user_id="u1",
        amount=Decimal("100"),
        currency=CurrencyType.MXN,
        transaction_type=TransactionType.EXPENSE,
        description="x",
        category=CategoryType.OTROS,
        transaction_date=date(2024, 12, 20),
        source="manual",
        created_at=datetime.now(UTC),
    )


class TestUpdateTransaction:
    async def test_serializes_only_provided_fields(self) -> None:
        repo = FakeRepository(stored=_stored_tx())
        service = TransactionService(repo, FakeCategorizer())

        await service.update_transaction(
            "tx-1", "u1", amount=Decimal("55.5"), category=CategoryType.VIAJES
        )

        tx_id, data = repo.updated[0]
        assert tx_id == "tx-1"
        assert data == {"amount": "55.5", "category": "viajes"}  # money as str, no other fields

    async def test_no_repo_update_when_no_fields(self) -> None:
        repo = FakeRepository(stored=_stored_tx())
        service = TransactionService(repo, FakeCategorizer())

        await service.update_transaction("tx-1", "u1")

        assert repo.updated == []

    async def test_raises_when_missing(self) -> None:
        repo = FakeRepository(stored=None)
        service = TransactionService(repo, FakeCategorizer())
        with pytest.raises(TransactionNotFoundError):
            await service.update_transaction("missing", "u1", amount=Decimal("1"))
        assert repo.updated == []


class TestDeleteTransaction:
    async def test_deletes_existing_and_returns_it(self) -> None:
        repo = FakeRepository(stored=_stored_tx())
        service = TransactionService(repo, FakeCategorizer())

        result = await service.delete_transaction("tx-1", "u1")

        assert repo.deleted == ["tx-1"]
        assert result.id == "tx-1"

    async def test_raises_when_missing(self) -> None:
        repo = FakeRepository(stored=None)
        service = TransactionService(repo, FakeCategorizer())
        with pytest.raises(TransactionNotFoundError):
            await service.delete_transaction("missing", "u1")
        assert repo.deleted == []


class TestListTransactions:
    async def test_computes_offset_and_returns_total(self) -> None:
        stored = Transaction(
            id="tx-1",
            user_id="u1",
            amount=Decimal("100"),
            currency=CurrencyType.MXN,
            transaction_type=TransactionType.EXPENSE,
            description="x",
            category=CategoryType.OTROS,
            transaction_date=date(2024, 12, 20),
            source="manual",
            created_at=datetime.now(UTC),
        )
        repo = FakeRepository(stored=stored, total=42)
        service = TransactionService(repo, FakeCategorizer())

        items, total = await service.list_transactions("u1", page=3, page_size=20)

        assert total == 42
        assert len(items) == 1
        assert repo.list_kwargs["offset"] == 40  # (3 - 1) * 20
        assert repo.list_kwargs["limit"] == 20
