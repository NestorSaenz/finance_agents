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
from app.src.transactions.services.transaction_service import (
    TransactionService,
    _match_category,
)


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
        self.recategorized: list[tuple[str, str]] = []
        self.deleted_categories: list[str] = []
        self.bulk_result = 0

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
            # Mirror the real repo: budget_date defaults to the purchase date.
            budget_date=transaction.budget_date or transaction.transaction_date,
            source=transaction.source,
            created_at=datetime.now(UTC),
        )

    async def create_occurrence(
        self, transaction: TransactionCreate, user_id: str
    ) -> Transaction | None:
        return await self.create(transaction, user_id)

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

    async def recategorize(self, user_id: str, old: str, new: str) -> int:
        self.recategorized.append((old, new))
        return self.bulk_result

    async def delete_by_category(self, user_id: str, category: str) -> int:
        self.deleted_categories.append(category)
        return self.bulk_result


def _new_transaction(category: CategoryType | None) -> TransactionCreate:
    return TransactionCreate(
        amount=Decimal("100"),
        description="Cena en restaurante",
        transaction_type=TransactionType.EXPENSE,
        transaction_date=date(2024, 12, 20),
        budget_date=date(2024, 12, 20),
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

    async def test_each_installment_uses_its_own_budget_month(self) -> None:
        # A deferred purchase's budget_date (the first statement's payment date)
        # must NOT be inherited by every installment; each cuota tracks its own month.
        repo = FakeRepository()
        service = TransactionService(repo, FakeCategorizer())
        base = _new_transaction(CategoryType.TECNOLOGIA).model_copy(
            update={"budget_date": date(2025, 9, 5)}  # whole-purchase payment date
        )

        created = await service.create_installments(base, 3, "u1")

        # Each installment's budget month == its own transaction month, not all Sep.
        assert [t.budget_date for t in created] == [
            date(2024, 12, 20),
            date(2025, 1, 20),
            date(2025, 2, 20),
        ]

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
        budget_date=date(2024, 12, 20),
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
            budget_date=date(2024, 12, 20),
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


def _tx(
    when: date,
    *,
    tx_type: TransactionType = TransactionType.EXPENSE,
    category: str = CategoryType.OTROS,
) -> Transaction:
    return Transaction(
        id=f"tx-{when.isoformat()}",
        user_id="u1",
        amount=Decimal("100"),
        currency=CurrencyType.MXN,
        transaction_type=tx_type,
        description="x",
        category=category,
        transaction_date=when,
        budget_date=when,
        source="manual",
        created_at=datetime.now(UTC),
    )


class _MultiRepo(FakeRepository):
    """Repository returning a fixed list, honoring the equality filters like the
    real repo, to exercise the service's in-period (date-range) filtering."""

    def __init__(self, items: list[Transaction]) -> None:
        super().__init__()
        self._items = items

    async def list_page(self, user_id: str, **kwargs: object) -> list[Transaction]:
        tx_type = kwargs.get("transaction_type")
        category = kwargs.get("category")
        return [
            t
            for t in self._items
            if (tx_type is None or t.transaction_type == tx_type)
            and (category is None or t.category == category)
        ]


class TestListByPeriod:
    async def test_keeps_only_in_range_and_sorts_newest_first(self) -> None:
        repo = _MultiRepo(
            [
                _tx(date(2026, 8, 10)),
                _tx(date(2026, 7, 30)),  # before the period
                _tx(date(2026, 8, 20)),
                _tx(date(2026, 9, 1)),  # after the period
            ]
        )
        service = TransactionService(repo, FakeCategorizer())

        result = await service.list_by_period(
            "u1", period_start=date(2026, 8, 1), period_end=date(2026, 8, 31)
        )

        assert [t.transaction_date for t in result] == [
            date(2026, 8, 20),
            date(2026, 8, 10),
        ]

    async def test_applies_type_and_category_filters(self) -> None:
        repo = _MultiRepo(
            [
                _tx(date(2026, 8, 5), category=CategoryType.TECNOLOGIA),
                _tx(date(2026, 8, 6), category=CategoryType.OTROS),
                _tx(date(2026, 8, 7), tx_type=TransactionType.INCOME),
            ]
        )
        service = TransactionService(repo, FakeCategorizer())

        result = await service.list_by_period(
            "u1",
            period_start=date(2026, 8, 1),
            period_end=date(2026, 8, 31),
            category=CategoryType.TECNOLOGIA,
        )

        assert [t.category for t in result] == [CategoryType.TECNOLOGIA]


class TestDeleteMovements:
    async def test_deletes_only_rows_in_the_date_range(self) -> None:
        repo = _MultiRepo(
            [
                _tx(date(2026, 7, 5)),
                _tx(date(2026, 7, 20)),
                _tx(date(2026, 6, 30)),  # before the range
                _tx(date(2026, 8, 1)),  # after the range
            ]
        )
        service = TransactionService(repo, FakeCategorizer())

        deleted = await service.delete_movements(
            "u1", period_start=date(2026, 7, 1), period_end=date(2026, 7, 31)
        )

        assert deleted == 2
        assert set(repo.deleted) == {"tx-2026-07-05", "tx-2026-07-20"}

    async def test_pushes_category_filter_and_normalizes(self) -> None:
        repo = _MultiRepo(
            [
                _tx(date(2026, 7, 5), category="transporte"),
                _tx(date(2026, 7, 6), category=CategoryType.OTROS),
            ]
        )
        service = TransactionService(repo, FakeCategorizer())

        deleted = await service.delete_movements(
            "u1",
            category="Transporte",  # normalized to "transporte" before the push-down
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 31),
        )

        assert deleted == 1
        assert repo.deleted == ["tx-2026-07-05"]

    async def test_refuses_when_no_filter_given(self) -> None:
        service = TransactionService(_MultiRepo([]), FakeCategorizer())

        with pytest.raises(ValueError):
            await service.delete_movements("u1")


class TestMatchCategory:
    def test_reuses_exact_existing_spelling(self) -> None:
        assert _match_category("mercado", ["mercado", "gym"]) == "mercado"

    def test_snaps_typo_to_existing(self) -> None:
        # "improvistos" is a typo of the user's existing "imprevistos".
        assert _match_category("improvistos", ["imprevistos", "mercado"]) == "imprevistos"

    def test_keeps_genuinely_new_category(self) -> None:
        assert _match_category("jardineria", ["mercado", "gym"]) == "jardineria"

    def test_does_not_merge_distinct_categories(self) -> None:
        # "ahorro" must NOT collapse into "ahorro carro" (they are different).
        assert _match_category("ahorro", ["ahorro carro"]) == "ahorro"

    def test_no_existing_returns_proposed(self) -> None:
        assert _match_category("mercado", []) == "mercado"


class TestResolveCategory:
    async def test_snaps_to_users_existing_category(self) -> None:
        repo = _MultiRepo(
            [_tx(date(2026, 8, 1), category="imprevistos"), _tx(date(2026, 8, 2))]
        )
        service = TransactionService(repo, FakeCategorizer())

        assert await service.resolve_category("improvistos", "u1") == "imprevistos"

    async def test_new_category_passes_through_normalized(self) -> None:
        repo = _MultiRepo([_tx(date(2026, 8, 1), category="mercado")])
        service = TransactionService(repo, FakeCategorizer())

        assert await service.resolve_category("  Jardinería  ", "u1") == "jardinería"


class TestBulkCategory:
    async def test_recategorize_normalizes_and_delegates(self) -> None:
        repo = FakeRepository()
        repo.bulk_result = 4
        service = TransactionService(repo, FakeCategorizer())

        moved = await service.recategorize("u1", " Improvistos ", "Imprevistos")

        assert moved == 4
        assert repo.recategorized == [("improvistos", "imprevistos")]  # normalized

    async def test_recategorize_noop_when_same(self) -> None:
        repo = FakeRepository()
        repo.bulk_result = 9
        service = TransactionService(repo, FakeCategorizer())

        moved = await service.recategorize("u1", "gym", "GYM")

        assert moved == 0
        assert repo.recategorized == []  # repo never touched

    async def test_delete_by_category_normalizes(self) -> None:
        repo = FakeRepository()
        repo.bulk_result = 2
        service = TransactionService(repo, FakeCategorizer())

        assert await service.delete_by_category("u1", " Imprevistos ") == 2
        assert repo.deleted_categories == ["imprevistos"]

    async def test_count_by_category(self) -> None:
        repo = FakeRepository(total=7)
        service = TransactionService(repo, FakeCategorizer())

        assert await service.count_by_category("u1", "imprevistos") == 7
