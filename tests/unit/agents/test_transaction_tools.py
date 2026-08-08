"""Unit tests for the transaction toolkit (service mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.agents.tools.transaction_tools import (
    ANALYZE_SPENDING_TOOL,
    DELETE_TRANSACTION_TOOL,
    QUERY_TRANSACTIONS_TOOL,
    REGISTER_TRANSACTION_TOOL,
    UPDATE_TRANSACTION_TOOL,
    TransactionToolkit,
)
from app.core.exceptions import TransactionNotFoundError
from app.shared.types import CategoryType, CurrencyType, PaymentMethod, TransactionType
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.transactions.models import SpendingSummary, Transaction, TransactionCreate
from tests.unit.agents.test_card_tools import FakeCardService, _card


def _transaction(
    category: CategoryType = CategoryType.RESTAURANTES,
    amount: Decimal = Decimal("50"),
    transaction_type: TransactionType = TransactionType.EXPENSE,
) -> Transaction:
    return Transaction(
        id="tx-1",
        user_id="u1",
        amount=amount,
        currency=CurrencyType.MXN,
        transaction_type=transaction_type,
        description="pizza",
        category=category,
        transaction_date=date(2024, 12, 20),
        source="manual",
        created_at=datetime(2024, 12, 20, tzinfo=UTC),
    )


class FakeTransactionService(TransactionServiceABC):
    def __init__(self) -> None:
        self.created: list[tuple[TransactionCreate, str]] = []
        self.list_calls: list[tuple[str, dict]] = []
        self.items: list[Transaction] = []
        self.total = 0
        self.updated: list[tuple[str, str, dict]] = []
        self.deleted: list[tuple[str, str]] = []
        self.not_found = False
        self.resolve_calls: list[tuple[str, str]] = []
        # When set, resolve_category returns this (simulates snapping to existing).
        self.resolved_category: str | None = None

    async def create_transaction(self, transaction: TransactionCreate, user_id: str) -> Transaction:
        self.created.append((transaction, user_id))
        return _transaction(transaction.category or CategoryType.OTROS)

    async def create_installments(
        self, base: TransactionCreate, installments: int, user_id: str
    ) -> list[Transaction]:
        per = base.amount / installments
        return [
            await self.create_transaction(base.model_copy(update={"amount": per}), user_id)
            for _ in range(installments)
        ]

    async def get_transaction(self, transaction_id: str, user_id: str) -> Transaction:
        return _transaction()

    async def list_transactions(self, user_id: str, **kwargs: object) -> tuple[list[Transaction], int]:
        self.list_calls.append((user_id, kwargs))
        return self.items, self.total

    async def list_by_period(self, user_id: str, **kwargs: object) -> list[Transaction]:
        return self.items

    async def resolve_category(self, proposed: str, user_id: str) -> str:
        self.resolve_calls.append((proposed, user_id))
        return self.resolved_category if self.resolved_category is not None else proposed

    async def count_by_category(self, user_id: str, category: str) -> int:
        return 0

    async def list_categories(self, user_id: str) -> list[str]:
        return []

    async def recategorize(self, user_id: str, old: str, new: str) -> int:
        return 0

    async def delete_by_category(self, user_id: str, category: str) -> int:
        return 0

    async def update_transaction(self, transaction_id: str, user_id: str, **kwargs: object) -> Transaction:
        if self.not_found:
            raise TransactionNotFoundError(transaction_id)
        self.updated.append((transaction_id, user_id, kwargs))
        return _transaction()

    async def delete_transaction(self, transaction_id: str, user_id: str) -> Transaction:
        if self.not_found:
            raise TransactionNotFoundError(transaction_id)
        self.deleted.append((transaction_id, user_id))
        return _transaction()

    async def get_spending_summary(self, user_id: str, **kwargs: object) -> SpendingSummary:
        raise NotImplementedError


class TestSchemas:
    def test_exposes_tools_without_user_id(self) -> None:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)

        names = {s["function"]["name"] for s in toolkit.schemas}
        assert names == {
            REGISTER_TRANSACTION_TOOL,
            QUERY_TRANSACTIONS_TOOL,
            ANALYZE_SPENDING_TOOL,
            UPDATE_TRANSACTION_TOOL,
            DELETE_TRANSACTION_TOOL,
        }

        # user_id must never be part of any tool's parameters.
        for schema in toolkit.schemas:
            assert "user_id" not in schema["function"]["parameters"]["properties"]


class TestRegister:
    async def test_registers_transaction(self) -> None:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)

        result = await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {
                "amount": 50,
                "description": "pizza",
                "transaction_type": "expense",
                "category": "restaurantes",
            },
            user_id="u1",
        )

        created, user_id = service.created[0]
        assert created.amount == Decimal("50")
        assert created.transaction_type == TransactionType.EXPENSE
        assert created.category == CategoryType.RESTAURANTES
        assert user_id == "u1"
        assert "pizza" in result

    async def test_custom_category_is_preserved_not_flattened(self) -> None:
        # A category outside the canonical enum must survive as a normalized string.
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {
                "amount": 50000,
                "description": "poda del jardín",
                "transaction_type": "expense",
                "category": "Jardinería",
            },
            user_id="u1",
        )

        created, _user = service.created[0]
        assert created.category == "jardinería"  # normalized (lowercased), not "otros"

    async def test_register_snaps_category_onto_existing(self) -> None:
        # A typo variant folds into the user's existing category via the service.
        service = FakeTransactionService()
        service.resolved_category = "imprevistos"
        toolkit = TransactionToolkit(service)

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {
                "amount": 90000,
                "description": "dollarcity",
                "transaction_type": "expense",
                "category": "improvistos",
            },
            user_id="u1",
        )

        # The normalized proposal reached resolve_category, and its result was stored.
        assert service.resolve_calls == [("improvistos", "u1")]
        created, _user = service.created[0]
        assert created.category == "imprevistos"

    async def test_omitted_category_defers_to_auto_categorization(self) -> None:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 50, "description": "pizza", "transaction_type": "expense"},
            user_id="u1",
        )

        assert service.created[0][0].category is None
        # Payment method is unknown when not stated.
        assert service.created[0][0].payment_method is None

    async def test_captures_credit_payment_method(self) -> None:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {
                "amount": 200,
                "description": "super",
                "transaction_type": "expense",
                "payment_method": "credito",
            },
            user_id="u1",
        )

        assert service.created[0][0].payment_method == PaymentMethod.CREDITO

    async def test_credit_with_several_cards_asks_which_without_registering(self) -> None:
        service = FakeTransactionService()
        cards = [_card("Rappid").model_copy(update={"id": "c1"}),
                 _card("Falabella").model_copy(update={"id": "c2"})]
        toolkit = TransactionToolkit(service, cards=FakeCardService(cards))

        result = await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 200, "description": "super", "transaction_type": "expense",
             "payment_method": "credito"},
            user_id="u1",
        )

        assert service.created == []  # not registered until the card is known
        assert "Rappid" in result and "Falabella" in result

    async def test_credit_with_named_card_links_and_registers(self) -> None:
        service = FakeTransactionService()
        cards = [_card("Rappid").model_copy(update={"id": "c1"}),
                 _card("Falabella").model_copy(update={"id": "c2"})]
        toolkit = TransactionToolkit(service, cards=FakeCardService(cards))

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 200, "description": "super", "transaction_type": "expense",
             "payment_method": "credito", "card_name": "rappid"},
            user_id="u1",
        )

        assert service.created[0][0].card_id == "c1"

    async def test_credit_with_single_card_auto_links(self) -> None:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(
            service, cards=FakeCardService([_card("Rappid").model_copy(update={"id": "c1"})])
        )

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 200, "description": "super", "transaction_type": "expense",
             "payment_method": "credito"},
            user_id="u1",
        )

        assert service.created[0][0].card_id == "c1"

    async def test_credit_with_unknown_card_name_asks(self) -> None:
        service = FakeTransactionService()
        cards = [_card("Rappid").model_copy(update={"id": "c1"}),
                 _card("Falabella").model_copy(update={"id": "c2"})]
        toolkit = TransactionToolkit(service, cards=FakeCardService(cards))

        result = await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 200, "description": "super", "transaction_type": "expense",
             "payment_method": "credito", "card_name": "Visa"},
            user_id="u1",
        )

        assert service.created == []
        assert "no encontré" in result.lower()

    async def test_cuotas_registers_one_transaction_per_month(self) -> None:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)

        result = await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 100000, "description": "nevera", "transaction_type": "expense",
             "category": "hogar", "cuotas": 4},
            user_id="u1",
        )

        assert len(service.created) == 4  # one per month, not one lump sum
        assert "4 cuotas" in result

    async def test_invalid_amount_returns_error_without_calling_service(self) -> None:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)

        result = await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 0, "description": "x", "transaction_type": "expense"},
            user_id="u1",
        )

        assert service.created == []
        assert "no pude registrar" in result.lower()

    async def test_user_id_from_model_is_ignored(self) -> None:
        """Security: a user_id injected in the model's arguments must be ignored."""
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {
                "amount": 50,
                "description": "pizza",
                "transaction_type": "expense",
                "user_id": "attacker",  # must be ignored
            },
            user_id="real-user",
        )

        assert service.created[0][1] == "real-user"


class TestQuery:
    async def test_formats_results(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction()]
        service.total = 1
        toolkit = TransactionToolkit(service)

        result = await toolkit.dispatch(
            QUERY_TRANSACTIONS_TOOL, {"transaction_type": "expense"}, user_id="u1"
        )

        assert "pizza" in result
        user_id, kwargs = service.list_calls[0]
        assert user_id == "u1"
        assert kwargs["transaction_type"] == TransactionType.EXPENSE

    async def test_empty_results(self) -> None:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)

        result = await toolkit.dispatch(QUERY_TRANSACTIONS_TOOL, {}, user_id="u1")

        assert "no se encontraron" in result.lower()


class TestAnalyze:
    async def test_aggregates_totals_and_by_category(self) -> None:
        service = FakeTransactionService()
        service.items = [
            _transaction(CategoryType.RESTAURANTES, Decimal("50")),
            _transaction(CategoryType.ALIMENTACION, Decimal("150")),
            _transaction(CategoryType.ALIMENTACION, Decimal("100")),
            _transaction(CategoryType.SALUD, Decimal("3000"), TransactionType.INCOME),
        ]
        toolkit = TransactionToolkit(service)

        # period="todo" avoids date filtering (fixed 2024 dates in the fake).
        result = await toolkit.dispatch(ANALYZE_SPENDING_TOOL, {"period": "todo"}, user_id="u1")

        assert "Ingresos: $3,000.00" in result
        assert "Gastos: $300.00" in result
        assert "Balance: $2,700.00" in result
        # Alimentación (250) is the biggest expense category and listed first.
        top_line = result.split("mayor a menor):")[1].strip().splitlines()[0]
        assert "limentación" in top_line and "250" in top_line

    async def test_empty_period_returns_message(self) -> None:
        service = FakeTransactionService()  # no items
        toolkit = TransactionToolkit(service)

        result = await toolkit.dispatch(ANALYZE_SPENDING_TOOL, {"period": "todo"}, user_id="u1")

        assert "no hay transacciones" in result.lower()


class TestUpdateDelete:
    async def test_delete_resolves_by_description(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction()]  # description "pizza", id "tx-1"
        result = await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL, {"description": "pizza"}, user_id="u1"
        )
        assert service.deleted == [("tx-1", "u1")]
        assert "elimin" in result.lower()

    async def test_delete_requires_description(self) -> None:
        service = FakeTransactionService()
        result = await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL, {}, user_id="u1"
        )
        assert service.deleted == []
        assert "no encontré" in result.lower()

    async def test_delete_no_match(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction()]
        result = await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL, {"description": "taxi"}, user_id="u1"
        )
        assert service.deleted == []
        assert "no encontré" in result.lower()

    async def test_update_resolves_and_sets_fields(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction()]
        result = await TransactionToolkit(service).dispatch(
            UPDATE_TRANSACTION_TOOL,
            {"description": "pizza", "new_amount": 99, "new_category": "viajes"},
            user_id="u1",
        )
        tx_id, user_id, fields = service.updated[0]
        assert tx_id == "tx-1" and user_id == "u1"
        assert fields["amount"] == Decimal("99")
        assert fields["category"] == CategoryType.VIAJES
        assert "actualic" in result.lower()

    async def test_update_snaps_category_onto_existing(self) -> None:
        # Re-categorizing to a typo variant folds into the existing category.
        service = FakeTransactionService()
        service.items = [_transaction()]
        service.resolved_category = "imprevistos"
        await TransactionToolkit(service).dispatch(
            UPDATE_TRANSACTION_TOOL,
            {"description": "pizza", "new_category": "improvistos"},
            user_id="u1",
        )
        assert service.resolve_calls == [("improvistos", "u1")]
        _tx_id, _user, fields = service.updated[0]
        assert fields["category"] == "imprevistos"

    async def test_update_sets_payment_method(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction()]
        await TransactionToolkit(service).dispatch(
            UPDATE_TRANSACTION_TOOL,
            {"description": "pizza", "payment_method": "efectivo"},
            user_id="u1",
        )
        _tx_id, _user, fields = service.updated[0]
        assert fields["payment_method"] == PaymentMethod.EFECTIVO

    async def test_update_requires_description(self) -> None:
        service = FakeTransactionService()
        result = await TransactionToolkit(service).dispatch(
            UPDATE_TRANSACTION_TOOL, {"new_amount": 10}, user_id="u1"
        )
        assert service.updated == []
        assert "no encontré" in result.lower()


class TestDispatch:
    async def test_unknown_tool_raises(self) -> None:
        toolkit = TransactionToolkit(FakeTransactionService())
        with pytest.raises(ValueError, match="Unknown transaction tool"):
            await toolkit.dispatch("nope", {}, user_id="u1")
