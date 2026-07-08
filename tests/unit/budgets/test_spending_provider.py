"""Unit tests for the transaction-based spending provider."""

from datetime import date
from decimal import Decimal

from app.shared.types import CategoryType
from app.src.budgets.services.spending_provider import TransactionSpendingProvider
from tests.fakes import FakeDatabase, make_transaction_row


class TestGetSpent:
    async def test_sums_only_transactions_within_period(self) -> None:
        rows = [
            make_transaction_row(id="t1", amount=100.0, transaction_date="2024-12-05"),
            make_transaction_row(id="t2", amount=250.0, transaction_date="2024-12-20"),
            make_transaction_row(id="t3", amount=999.0, transaction_date="2024-11-30"),  # before
            make_transaction_row(id="t4", amount=999.0, transaction_date="2025-01-02"),  # after
        ]
        provider = TransactionSpendingProvider(FakeDatabase(rows=rows))

        spent = await provider.get_spent(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )

        assert spent == Decimal("350.0")

    async def test_filters_include_expense_and_category(self) -> None:
        db = FakeDatabase(rows=[])
        provider = TransactionSpendingProvider(db)

        await provider.get_spent(
            "u1", CategoryType.TRANSPORTE, date(2024, 12, 1), date(2024, 12, 31)
        )

        config = db.select_configs[-1]
        assert config.filters == {"user_id": "u1", "type": "expense", "category": "transporte"}

    async def test_overall_budget_has_no_category_filter(self) -> None:
        db = FakeDatabase(rows=[])
        provider = TransactionSpendingProvider(db)

        await provider.get_spent("u1", None, date(2024, 12, 1), date(2024, 12, 31))

        assert "category" not in db.select_configs[-1].filters

    async def test_empty_returns_zero(self) -> None:
        provider = TransactionSpendingProvider(FakeDatabase(rows=[]))
        spent = await provider.get_spent(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )
        assert spent == Decimal("0")

    async def test_uses_server_side_rpc_when_available(self) -> None:
        # When the sum_expenses RPC returns a value, use it and skip the row scan.
        db = FakeDatabase(rows=[])
        db.rpc_result = [3200.5]
        provider = TransactionSpendingProvider(db)

        spent = await provider.get_spent(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )

        assert spent == Decimal("3200.5")
        name, params = db.rpc_calls[-1]
        assert name == "sum_expenses"
        assert params == {
            "p_user_id": "u1",
            "p_category": "restaurantes",
            "p_start": "2024-12-01",
            "p_end": "2024-12-31",
        }
        assert db.select_configs == []  # no full-table scan when the RPC answered
