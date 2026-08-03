"""Unit tests for the transaction service (repository + categorizer mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.exceptions import TransactionNotFoundError
from app.shared.types import CategoryType, CurrencyType, PaymentMethod, TransactionType
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


class TestCreateInstallments:
    async def test_splits_amount_exactly_across_months(self) -> None:
        repo = FakeRepository()
        service = TransactionService(repo, FakeCategorizer())

        parts = await service.create_installments(_new_transaction(CategoryType.TECNOLOGIA), 3, "u1")

        assert len(parts) == 3
        amounts = [t.amount for t in repo.created]
        # First two equal; the last absorbs the rounding remainder → sums exactly to 100.
        assert amounts == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
        assert sum(amounts) == Decimal("100")

    async def test_dates_advance_one_month_each(self) -> None:
        repo = FakeRepository()
        service = TransactionService(repo, FakeCategorizer())

        await service.create_installments(_new_transaction(CategoryType.TECNOLOGIA), 3, "u1")

        dates = [t.transaction_date for t in repo.created]
        assert dates == [date(2024, 12, 20), date(2025, 1, 20), date(2025, 2, 20)]

    async def test_labels_each_installment(self) -> None:
        repo = FakeRepository()
        service = TransactionService(repo, FakeCategorizer())

        await service.create_installments(_new_transaction(CategoryType.TECNOLOGIA), 3, "u1")

        assert [t.description for t in repo.created] == [
            "Cena en restaurante (cuota 1/3)",
            "Cena en restaurante (cuota 2/3)",
            "Cena en restaurante (cuota 3/3)",
        ]

    async def test_categorizes_once_for_all_installments(self) -> None:
        repo = FakeRepository()
        categorizer = FakeCategorizer(CategoryType.RESTAURANTES)
        service = TransactionService(repo, categorizer)

        await service.create_installments(_new_transaction(None), 4, "u1")

        assert categorizer.called_with == ["Cena en restaurante"]  # a single call, not four
        assert all(t.category == CategoryType.RESTAURANTES for t in repo.created)

    async def test_clamps_day_to_month_length(self) -> None:
        repo = FakeRepository()
        service = TransactionService(repo, FakeCategorizer())
        base = _new_transaction(CategoryType.TECNOLOGIA).model_copy(
            update={"transaction_date": date(2025, 1, 31)}
        )

        await service.create_installments(base, 2, "u1")

        # Jan 31 + 1 month → Feb 28 (2025 is not a leap year).
        assert repo.created[1].transaction_date == date(2025, 2, 28)

    async def test_installments_keep_card_and_payment_method(self) -> None:
        repo = FakeRepository()
        service = TransactionService(repo, FakeCategorizer())
        base = _new_transaction(CategoryType.TECNOLOGIA).model_copy(
            update={"payment_method": PaymentMethod.CREDITO, "card_id": "card-1"}
        )

        await service.create_installments(base, 3, "u1")

        # A deferred purchase is on credit: every installment keeps the card and method.
        assert all(t.payment_method == PaymentMethod.CREDITO for t in repo.created)
        assert all(t.card_id == "card-1" for t in repo.created)


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
