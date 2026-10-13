"""Unit tests for the transaction-based spending provider."""

from datetime import date
from decimal import Decimal

import pytest

from app.shared.types import CategoryType
from app.src.budgets.services.spending_provider import TransactionSpendingProvider
from tests.fakes import FakeDatabase, make_transaction_row


class TestGetSpending:
    async def test_sums_only_transactions_within_period(self) -> None:
        rows = [
            make_transaction_row(id="t1", amount=100.0, transaction_date="2024-12-05"),
            make_transaction_row(id="t2", amount=250.0, transaction_date="2024-12-20"),
            make_transaction_row(id="t3", amount=999.0, transaction_date="2024-11-30"),  # before
            make_transaction_row(id="t4", amount=999.0, transaction_date="2025-01-02"),  # after
        ]
        provider = TransactionSpendingProvider(FakeDatabase(rows=rows))

        spent = await provider.get_spending(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )

        assert spent.total == Decimal("350.0")
        assert spent.fixed == Decimal("0")

    async def test_fallback_attributes_by_budget_date(self) -> None:
        # Budgets sum by budget_date (credit -> payment month), not purchase date.
        rows = [
            # Bought in November (out of range) but paid in December -> counts.
            make_transaction_row(
                id="t1", amount=100.0, transaction_date="2024-11-22", budget_date="2024-12-05"
            ),
            # Bought in December but paid in January (budget out of range) -> excluded.
            make_transaction_row(
                id="t2", amount=999.0, transaction_date="2024-12-28", budget_date="2025-01-05"
            ),
        ]
        provider = TransactionSpendingProvider(FakeDatabase(rows=rows))

        spent = await provider.get_spending(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )

        assert spent.total == Decimal("100.0")

    async def test_fallback_counts_recurring_as_fixed(self) -> None:
        # Recurring rows now COUNT in the total and are also reported as fixed
        # (parity with the budget_spending RPC); budget_date attribution is kept.
        rows = [
            make_transaction_row(id="t1", amount=100.0, transaction_date="2024-12-05"),
            make_transaction_row(
                id="t2", amount=250.0, transaction_date="2024-12-10", recurring_id="rec-1"
            ),
            # Recurring row paid next month via budget_date -> out of range.
            make_transaction_row(
                id="t3",
                amount=500.0,
                transaction_date="2024-12-28",
                budget_date="2025-01-05",
                recurring_id="rec-2",
            ),
            # Missing budget_date falls back to transaction_date.
            make_transaction_row(
                id="t4", amount=40.0, transaction_date="2024-12-12", budget_date=None
            ),
        ]
        provider = TransactionSpendingProvider(FakeDatabase(rows=rows))

        spent = await provider.get_spending(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )

        assert spent.total == Decimal("390.0")
        assert spent.fixed == Decimal("250.0")
        assert spent.variable == Decimal("140.0")

    async def test_fallback_selects_recurring_id(self) -> None:
        db = FakeDatabase(rows=[])
        provider = TransactionSpendingProvider(db)

        await provider.get_spending(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )

        assert "recurring_id" in db.select_configs[-1].select

    async def test_filters_include_expense_and_category(self) -> None:
        db = FakeDatabase(rows=[])
        provider = TransactionSpendingProvider(db)

        await provider.get_spending(
            "u1", CategoryType.TRANSPORTE, date(2024, 12, 1), date(2024, 12, 31)
        )

        config = db.select_configs[-1]
        assert config.filters == {"user_id": "u1", "type": "expense", "category": "transporte"}

    async def test_overall_budget_has_no_category_filter(self) -> None:
        db = FakeDatabase(rows=[])
        provider = TransactionSpendingProvider(db)

        await provider.get_spending("u1", None, date(2024, 12, 1), date(2024, 12, 31))

        assert "category" not in db.select_configs[-1].filters

    async def test_empty_returns_zero(self) -> None:
        provider = TransactionSpendingProvider(FakeDatabase(rows=[]))
        spent = await provider.get_spending(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )
        assert spent.total == Decimal("0")
        assert spent.fixed == Decimal("0")

    async def test_uses_server_side_rpc_when_available(self) -> None:
        # When budget_spending returns a row, use it and skip the row scan.
        db = FakeDatabase(rows=[])
        db.rpc_result = [{"total": 3200.5, "fixed": "1000"}]
        provider = TransactionSpendingProvider(db)

        spent = await provider.get_spending(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )

        assert spent.total == Decimal("3200.5")
        assert spent.fixed == Decimal("1000")
        name, params = db.rpc_calls[-1]
        assert name == "budget_spending"
        assert params == {
            "p_user_id": "u1",
            "p_category": "restaurantes",
            "p_start": "2024-12-01",
            "p_end": "2024-12-31",
        }
        assert db.select_configs == []  # no full-table scan when the RPC answered

    @pytest.mark.parametrize(
        "bad_row",
        [
            {"total": "abc", "fixed": 0},
            {"total": 100},
            {"total": None, "fixed": None},
            "3200.5",
            3200.5,
        ],
    )
    async def test_malformed_rpc_row_falls_back_to_scan(self, bad_row: object) -> None:
        db = FakeDatabase(
            rows=[make_transaction_row(id="t1", amount=70.0, transaction_date="2024-12-05")]
        )
        db.rpc_result = [bad_row]  # type: ignore[list-item]
        provider = TransactionSpendingProvider(db)

        spent = await provider.get_spending(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )

        assert spent.total == Decimal("70.0")
        assert len(db.select_configs) == 1

    async def test_rpc_error_falls_back_to_scan(self) -> None:
        class FailingRpcDatabase(FakeDatabase):
            async def execute_rpc(self, function_name, params):  # type: ignore[no-untyped-def]
                raise RuntimeError("function budget_spending does not exist")

        db = FailingRpcDatabase(
            rows=[
                make_transaction_row(
                    id="t1", amount=80.0, transaction_date="2024-12-05", recurring_id="r1"
                )
            ]
        )
        provider = TransactionSpendingProvider(db)

        spent = await provider.get_spending(
            "u1", CategoryType.RESTAURANTES, date(2024, 12, 1), date(2024, 12, 31)
        )

        assert spent.total == Decimal("80.0")
        assert spent.fixed == Decimal("80.0")
