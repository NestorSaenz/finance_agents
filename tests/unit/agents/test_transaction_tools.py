"""Unit tests for the transaction toolkit (service mocked)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.agents.tools.transaction_tools import (
    ANALYZE_SPENDING_TOOL,
    DELETE_BY_FILTER_TOOL,
    DELETE_TRANSACTION_TOOL,
    QUERY_TRANSACTIONS_TOOL,
    REGISTER_TRANSACTION_TOOL,
    UPDATE_TRANSACTION_TOOL,
    TransactionToolkit,
    _credit_budget_date,
)
from app.core.exceptions import BudgetNotFoundError, TransactionNotFoundError
from app.shared.types import (
    BudgetPeriod,
    CategoryType,
    CurrencyType,
    PaymentMethod,
    TransactionType,
)
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.budgets.models import Budget, BudgetCreate, BudgetStatus
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
        budget_date=date(2024, 12, 20),
        source="manual",
        created_at=datetime(2024, 12, 20, tzinfo=UTC),
    )


def _cuota_tx(
    base: str,
    index: int,
    total: int,
    amount: Decimal = Decimal("54073"),
    tx_id: str = "tx",
) -> Transaction:
    """One installment row, named '<base> (cuota index/total)', dated a month apart."""
    return Transaction(
        id=tx_id,
        user_id="u1",
        amount=amount,
        currency=CurrencyType.MXN,
        transaction_type=TransactionType.EXPENSE,
        description=f"{base} (cuota {index}/{total})",
        category=CategoryType.OTROS,
        transaction_date=date(2026, min(6 + index - 1, 12), 21),
        budget_date=date(2026, min(6 + index - 1, 12), 21),
        source="manual",
        created_at=datetime(2026, 6, 21, tzinfo=UTC),
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
        # Reflect the input so callers (e.g. the budget nudge) see the real
        # amount/type/dates, mirroring what the repository would persist.
        return _transaction(
            transaction.category or CategoryType.OTROS,
            amount=transaction.amount,
            transaction_type=transaction.transaction_type,
        ).model_copy(
            update={
                "description": transaction.description,
                "transaction_date": transaction.transaction_date,
                "budget_date": transaction.budget_date or transaction.transaction_date,
            }
        )

    async def categorize(self, description: str) -> str:
        return CategoryType.OTROS.value

    async def materialize_occurrence(
        self, transaction: TransactionCreate, user_id: str
    ) -> Transaction | None:
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

    async def delete_movements(self, user_id: str, **kwargs: object) -> int:
        self.deleted_movements = kwargs
        return len(self.items)

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


def _budget(
    amount: Decimal = Decimal("1000"),
    alert_threshold: Decimal = Decimal("80"),
    alert_enabled: bool = True,
    name: str = "Restaurantes",
    category: str = "restaurantes",
) -> Budget:
    return Budget(
        id="b1",
        user_id="u1",
        name=name,
        amount=amount,
        category=category,
        currency=CurrencyType.MXN,
        period_type=BudgetPeriod.MONTHLY,
        start_date=date(2026, 8, 1),
        end_date=None,
        alert_threshold=alert_threshold,
        alert_enabled=alert_enabled,
        is_active=True,
        created_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def _status(
    budget: Budget,
    spent: Decimal,
    percentage: float,
    period_start: date = date(2026, 8, 1),
    period_end: date = date(2026, 8, 31),
) -> BudgetStatus:
    threshold_amt = budget.amount * budget.alert_threshold / 100
    return BudgetStatus(
        budget=budget,
        period_start=period_start,
        period_end=period_end,
        spent=spent,
        remaining=budget.amount - spent,
        percentage=percentage,
        alert_triggered=spent >= threshold_amt,
    )


class FakeBudgetService(BudgetServiceABC):
    """Budget service stub: only resolve_budget + get_budget_status are real."""

    def __init__(
        self,
        budget: Budget | None = None,
        status: BudgetStatus | None = None,
        raise_on_status: bool = False,
    ) -> None:
        self._budget = budget
        self._status = status
        self._raise_on_status = raise_on_status

    async def resolve_budget(self, reference: str, user_id: str) -> Budget | None:
        return self._budget

    async def get_budget_status(
        self, budget_id: str, user_id: str, as_of: date | None = None
    ) -> BudgetStatus:
        if self._raise_on_status:
            raise BudgetNotFoundError(budget_id)
        assert self._status is not None
        return self._status

    # --- unused abstract methods (not exercised by the nudge) ---
    async def create_budget(self, budget: BudgetCreate, user_id: str) -> Budget:
        raise NotImplementedError

    async def get_budget(self, budget_id: str, user_id: str) -> Budget:
        raise NotImplementedError

    async def list_budgets(
        self, user_id: str, *, page: int, page_size: int
    ) -> tuple[list[Budget], int]:
        raise NotImplementedError

    async def get_active_alerts(
        self, user_id: str, as_of: date | None = None
    ) -> list[BudgetStatus]:
        raise NotImplementedError

    async def get_all_status(
        self, user_id: str, as_of: date | None = None
    ) -> list[BudgetStatus]:
        raise NotImplementedError

    async def update_budget(
        self,
        budget_id: str,
        user_id: str,
        *,
        name: str | None = None,
        amount: Decimal | None = None,
    ) -> Budget:
        raise NotImplementedError

    async def delete_budget(self, budget_id: str, user_id: str) -> Budget:
        raise NotImplementedError

    async def recategorize(self, user_id: str, old: str, new: str) -> int:
        raise NotImplementedError

    async def delete_by_category(self, user_id: str, category: str) -> int:
        raise NotImplementedError


class TestBudgetNudge:
    async def _register_expense(
        self, budgets: FakeBudgetService, *, amount: int = 100, tx_type: str = "expense"
    ) -> str:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service, budgets=budgets)
        return await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {
                "amount": amount,
                "description": "pizza",
                "transaction_type": tx_type,
                "category": "restaurantes",
                "transaction_date": "2026-08-15",
            },
            user_id="u1",
        )

    async def test_expense_crossing_threshold_appends_percentage_nudge(self) -> None:
        budget = _budget(amount=Decimal("1000"), alert_threshold=Decimal("80"))
        status = _status(budget, spent=Decimal("820"), percentage=82.0)  # before=720
        result = await self._register_expense(FakeBudgetService(budget, status))

        assert "vas al 82%" in result
        assert "⚠️" in result

    async def test_expense_well_under_budget_has_no_nudge(self) -> None:
        budget = _budget(amount=Decimal("1000"), alert_threshold=Decimal("80"))
        status = _status(budget, spent=Decimal("200"), percentage=20.0)  # before=150
        result = await self._register_expense(FakeBudgetService(budget, status), amount=50)

        assert "⚠️" not in result

    async def test_expense_crossing_100_percent_appends_over_budget_nudge(self) -> None:
        budget = _budget(amount=Decimal("1000"), alert_threshold=Decimal("80"))
        status = _status(budget, spent=Decimal("1050"), percentage=105.0)  # before=950
        result = await self._register_expense(FakeBudgetService(budget, status))

        assert "te pasaste" in result
        assert "⚠️" in result

    async def test_no_budget_for_category_has_no_nudge(self) -> None:
        result = await self._register_expense(FakeBudgetService(budget=None))

        assert "⚠️" not in result

    async def test_alert_disabled_has_no_nudge(self) -> None:
        budget = _budget(alert_enabled=False)
        status = _status(budget, spent=Decimal("900"), percentage=90.0)
        result = await self._register_expense(FakeBudgetService(budget, status))

        assert "⚠️" not in result

    async def test_income_never_nudges(self) -> None:
        budget = _budget()
        status = _status(budget, spent=Decimal("900"), percentage=90.0)
        result = await self._register_expense(
            FakeBudgetService(budget, status), amount=5000, tx_type="income"
        )

        assert "⚠️" not in result

    async def test_status_error_still_returns_confirmation(self) -> None:
        budget = _budget()
        budgets = FakeBudgetService(budget, status=None, raise_on_status=True)
        result = await self._register_expense(budgets)

        assert "registré" in result.lower()
        assert "⚠️" not in result

    async def test_toolkit_without_budgets_has_no_nudge(self) -> None:
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service)  # no budgets wired

        result = await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {
                "amount": 100,
                "description": "pizza",
                "transaction_type": "expense",
                "category": "restaurantes",
            },
            user_id="u1",
        )

        assert "⚠️" not in result


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
            DELETE_BY_FILTER_TOOL,
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

    async def test_register_with_card_name_links_card_as_credit(self) -> None:
        # Naming a card must link it (and mark the charge as credit) even when the
        # model didn't set payment_method — otherwise it registers unlinked.
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service, cards=FakeCardService())

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {
                "amount": 94800,
                "description": "Wompi",
                "transaction_type": "expense",
                "card_name": "visa",
            },
            user_id="u1",
        )

        created, _ = service.created[0]
        assert created.card_id == "card-1"
        assert created.payment_method == PaymentMethod.CREDITO

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
        # No card on file → an expense with no stated method can only be cash.
        toolkit = TransactionToolkit(service, cards=FakeCardService(cards=[]))

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 50, "description": "pizza", "transaction_type": "expense"},
            user_id="u1",
        )

        assert service.created[0][0].category is None
        # No cards → default to efectivo (no follow-up question).
        assert service.created[0][0].payment_method == PaymentMethod.EFECTIVO

    async def test_expense_without_method_defaults_to_cash_when_no_cards(self) -> None:
        # A user with no registered cards never gets asked "¿efectivo o crédito?" —
        # the charge can only be cash, so it's registered as efectivo straight away.
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service, cards=FakeCardService(cards=[]))

        result = await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 100, "description": "jardinería", "transaction_type": "expense"},
            user_id="u1",
        )

        assert len(service.created) == 1  # registered straight away, no question
        assert service.created[0][0].payment_method == PaymentMethod.EFECTIVO
        assert "registré" in result.lower()

    async def test_expense_without_method_asks_when_user_has_cards(self) -> None:
        # With cards on file we ask instead of registering, so a pm-less row isn't
        # created now and re-created when the user answers "con tarjeta" (the dup bug).
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service, cards=FakeCardService())  # one card

        result = await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 100, "description": "jardinería", "transaction_type": "expense"},
            user_id="u1",
        )

        assert service.created == []  # nothing registered until the method is known
        assert "efectivo" in result.lower() and "crédito" in result.lower()

    async def test_income_without_method_registers_directly(self) -> None:
        # Income needs no payment method — it must never trigger the cash/credit ask.
        service = FakeTransactionService()
        toolkit = TransactionToolkit(service, cards=FakeCardService())  # has cards

        await toolkit.dispatch(
            REGISTER_TRANSACTION_TOOL,
            {"amount": 5000, "description": "sueldo", "transaction_type": "income"},
            user_id="u1",
        )

        assert service.created[0][0].transaction_type == TransactionType.INCOME

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

    async def test_filters_by_period_and_payment_method(self) -> None:
        # "transporte en efectivo en junio" must return ONLY June cash rows, all of
        # them (the bug: the agent could not filter by month or payment method).
        service = FakeTransactionService()
        service.items = [
            _transaction().model_copy(
                update={
                    "id": "a", "transaction_date": date(2026, 6, 30),
                    "amount": Decimal("2537250"), "payment_method": PaymentMethod.EFECTIVO,
                    "description": "transporte", "category": "transporte",
                }
            ),
            _transaction().model_copy(
                update={
                    "id": "b", "transaction_date": date(2026, 6, 15),
                    "amount": Decimal("5200"), "payment_method": PaymentMethod.CREDITO,
                    "description": "Flypass", "category": "transporte",
                }
            ),
            _transaction().model_copy(
                update={
                    "id": "c", "transaction_date": date(2026, 7, 2),
                    "amount": Decimal("100"), "payment_method": PaymentMethod.EFECTIVO,
                    "description": "otro", "category": "transporte",
                }
            ),
        ]

        result = await TransactionToolkit(service).dispatch(
            QUERY_TRANSACTIONS_TOOL,
            {"period": "2026-06", "payment_method": "efectivo"},
            user_id="u1",
        )

        assert "2537250" in result  # June cash row included
        assert "Flypass" not in result  # June credit excluded
        assert "otro" not in result  # July excluded
        assert "1 transacción" in result  # count reflects the filtered set

    async def test_invalid_period_asks_for_clarification(self) -> None:
        # An unrecognized month ("junio") must not silently return the current
        # month; the tool asks for a valid format instead.
        service = FakeTransactionService()
        service.items = [_transaction()]
        result = await TransactionToolkit(service).dispatch(
            QUERY_TRANSACTIONS_TOOL, {"period": "junio"}, user_id="u1"
        )
        assert "de qué mes" in result.lower()

    async def test_efectivo_filter_includes_untagged_cashless(self) -> None:
        # A cash row registered without the word "efectivo" (payment_method None,
        # no card) still counts as efectivo; an untagged card charge does not.
        service = FakeTransactionService()
        service.items = [
            _transaction().model_copy(
                update={
                    "id": "cash", "description": "consulta",
                    "payment_method": None, "card_id": None,
                }
            ),
            _transaction().model_copy(
                update={
                    "id": "card", "description": "cargo nu",
                    "payment_method": None, "card_id": "nu-1",
                }
            ),
        ]
        result = await TransactionToolkit(service).dispatch(
            QUERY_TRANSACTIONS_TOOL, {"payment_method": "efectivo"}, user_id="u1"
        )
        assert "consulta" in result  # untagged + no card -> treated as cash
        assert "cargo nu" not in result  # untagged but card-linked -> credit


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
        assert "qué gasto" in result.lower()

    async def test_delete_no_match(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction()]
        result = await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL, {"description": "taxi"}, user_id="u1"
        )
        assert service.deleted == []
        assert "no encontré" in result.lower()

    async def test_delete_matches_by_category(self) -> None:
        # The user refers to the category ("venezuela") but the row is described
        # "MERCA FACIL"; matching must consider the category, not only the description.
        service = FakeTransactionService()
        service.items = [
            _transaction().model_copy(
                update={
                    "id": "v1", "description": "MERCA FACIL",
                    "category": "venezuela", "amount": Decimal("238290"),
                }
            )
        ]
        await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL,
            {"description": "venezuela", "amount": 238290},
            user_id="u1",
        )
        assert ("v1", "u1") in service.deleted

    async def test_delete_matches_when_term_longer_than_stored(self) -> None:
        # The agent passes a longer label ("envío a venezuela") than the stored
        # description ("Venezuela"); the match must work in that direction too.
        service = FakeTransactionService()
        service.items = [
            _transaction().model_copy(
                update={
                    "id": "vz", "description": "Venezuela", "category": "venezuela",
                    "amount": Decimal("1250000"), "transaction_date": date(2026, 7, 15),
                }
            )
        ]
        await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL,
            {
                "description": "envío a venezuela",
                "amount": 1250000,
                "transaction_date": "2026-07-15",
            },
            user_id="u1",
        )
        assert ("vz", "u1") in service.deleted

    async def test_delete_removes_all_installments(self) -> None:
        # A deferred purchase is stored as N rows; deleting it must remove them all,
        # not just one cuota (the bug users hit with installments).
        service = FakeTransactionService()
        service.items = [
            _cuota_tx("Playstation Network", i, 3, tx_id=f"ps-{i}") for i in (1, 2, 3)
        ]
        result = await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL, {"description": "playstation"}, user_id="u1"
        )
        assert {tx_id for tx_id, _ in service.deleted} == {"ps-1", "ps-2", "ps-3"}
        assert "3 cuota" in result.lower()

    async def test_delete_installment_by_total_amount(self) -> None:
        # The user gives the TOTAL of the purchase; each row holds the per-cuota
        # value, so the total must resolve to the group (not fail to match).
        service = FakeTransactionService()
        service.items = [
            _cuota_tx("Sport Line", i, 2, amount=Decimal("100000"), tx_id=f"sp-{i}")
            for i in (1, 2)
        ]
        result = await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL,
            {"description": "sport line", "amount": 200000},
            user_id="u1",
        )
        assert {tx_id for tx_id, _ in service.deleted} == {"sp-1", "sp-2"}
        assert "2 cuota" in result.lower()

    async def test_delete_installment_ignores_date_and_removes_group(self) -> None:
        # A date must not split a cuota purchase down to one row; the whole group
        # still goes (dates differ per cuota, so a date would otherwise orphan them).
        service = FakeTransactionService()
        service.items = [
            _cuota_tx("Playstation Network", i, 3, tx_id=f"ps-{i}") for i in (1, 2, 3)
        ]
        await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL,
            {"description": "playstation", "transaction_date": "2026-07-21"},
            user_id="u1",
        )
        assert {tx_id for tx_id, _ in service.deleted} == {"ps-1", "ps-2", "ps-3"}

    async def test_delete_dedups_duplicate_installment_groups(self) -> None:
        # A purchase registered twice leaves duplicate cuota rows; deleting the
        # purchase clears every row so no orphan cuotas remain.
        service = FakeTransactionService()
        service.items = [
            _cuota_tx("Playstation Network", 1, 2, tx_id="a1"),
            _cuota_tx("Playstation Network", 2, 2, tx_id="a2"),
            _cuota_tx("Playstation Network", 1, 2, tx_id="b1"),  # duplicate registration
            _cuota_tx("Playstation Network", 2, 2, tx_id="b2"),
        ]
        await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL, {"description": "playstation"}, user_id="u1"
        )
        assert {tx_id for tx_id, _ in service.deleted} == {"a1", "a2", "b1", "b2"}

    async def test_delete_many_by_items_list(self) -> None:
        # A list of descriptors deletes each specific gasto in one call; misses are
        # reported, not silently dropped.
        service = FakeTransactionService()
        service.items = [
            _transaction().model_copy(update={"id": "t1", "description": "pizza"}),
            _transaction().model_copy(update={"id": "t2", "description": "taxi"}),
            _transaction().model_copy(update={"id": "t3", "description": "cafe"}),
        ]
        result = await TransactionToolkit(service).dispatch(
            DELETE_TRANSACTION_TOOL,
            {
                "items": [
                    {"description": "pizza"},
                    {"description": "taxi"},
                    {"description": "no-existe"},
                ]
            },
            user_id="u1",
        )
        assert {tx_id for tx_id, _ in service.deleted} == {"t1", "t2"}
        assert "no-existe" in result.lower()  # the miss is surfaced

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

    async def test_update_income_replaces_amount_not_registers(self) -> None:
        # "actualiza mi ingreso a 22M" must UPDATE the income transaction (like an
        # expense), never register a new one (which would sum on top).
        service = FakeTransactionService()
        service.items = [
            _transaction(transaction_type=TransactionType.INCOME).model_copy(
                update={
                    "id": "inc",
                    "description": "ingreso mensual",
                    "amount": Decimal("14000000"),
                }
            )
        ]
        await TransactionToolkit(service).dispatch(
            UPDATE_TRANSACTION_TOOL,
            {"description": "ingreso", "new_amount": 22000000},
            user_id="u1",
        )
        assert service.created == []  # nothing was registered
        tx_id, _uid, fields = service.updated[0]
        assert tx_id == "inc"
        assert fields["amount"] == Decimal("22000000")

    async def test_update_matches_accent_insensitive(self) -> None:
        # "bunuelos" (no ñ) must resolve "buñuelos" so a re-categorization lands.
        service = FakeTransactionService()
        service.items = [
            _transaction().model_copy(
                update={
                    "id": "bn", "description": "buñuelos",
                    "category": "otros", "amount": Decimal("2600"),
                }
            )
        ]
        await TransactionToolkit(service).dispatch(
            UPDATE_TRANSACTION_TOOL,
            {"description": "bunuelos", "new_category": "gastos casa"},
            user_id="u1",
        )
        assert service.updated  # resolved despite the missing tilde
        _tid, _uid, fields = service.updated[0]
        assert fields["category"] == "gastos casa"

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


class TestCreditBudgetDate:
    def test_credit_purchase_after_cutoff_rolls_to_payment_month(self) -> None:
        # Card cutoff 15, payment 5. Purchase Jul 22 -> statement closes Aug 15
        # -> paid Sep 5 -> budget impact = September.
        assert _credit_budget_date(_card(), date(2026, 7, 22)) == date(2026, 9, 5)

    def test_credit_purchase_before_cutoff_pays_next_month(self) -> None:
        # Purchase Jul 10 -> statement closes Jul 15 -> paid Aug 5.
        assert _credit_budget_date(_card(), date(2026, 7, 10)) == date(2026, 8, 5)

    def test_cash_keeps_purchase_date(self) -> None:
        assert _credit_budget_date(None, date(2026, 7, 22)) == date(2026, 7, 22)


class TestCardScopedOps:
    async def test_query_filters_by_card(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction()]
        toolkit = TransactionToolkit(service, cards=FakeCardService())

        await toolkit.dispatch(
            QUERY_TRANSACTIONS_TOOL, {"card_name": "Visa BBVA"}, user_id="u1"
        )

        _uid, kwargs = service.list_calls[-1]
        assert kwargs["card_id"] == "card-1"

    async def test_query_shows_card_name(self) -> None:
        # A charge must report its card by name (not just "credito"), so the agent
        # can tell the user which card a transaction — e.g. a cuota — belongs to.
        service = FakeTransactionService()
        service.items = [_transaction().model_copy(update={"card_id": "card-1"})]
        service.total = 1
        toolkit = TransactionToolkit(service, cards=FakeCardService())

        result = await toolkit.dispatch(QUERY_TRANSACTIONS_TOOL, {}, user_id="u1")

        assert "Visa BBVA" in result

    async def test_query_unknown_card_returns_message(self) -> None:
        toolkit = TransactionToolkit(FakeTransactionService(), cards=FakeCardService(cards=[]))

        result = await toolkit.dispatch(
            QUERY_TRANSACTIONS_TOOL, {"card_name": "Nu"}, user_id="u1"
        )

        assert "no encontré" in result.lower()

    async def test_delete_movements_by_card_and_period(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction(), _transaction()]
        toolkit = TransactionToolkit(service, cards=FakeCardService())

        result = await toolkit.dispatch(
            DELETE_BY_FILTER_TOOL,
            {"card_name": "Visa BBVA", "period": "2026-08"},
            user_id="u1",
        )

        assert service.deleted_movements["card_id"] == "card-1"
        assert "2" in result

    async def test_delete_movements_by_category_and_period(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction(), _transaction(), _transaction()]
        toolkit = TransactionToolkit(service, cards=FakeCardService())

        result = await toolkit.dispatch(
            DELETE_BY_FILTER_TOOL,
            {"category": "transporte", "period": "2026-07"},
            user_id="u1",
        )

        assert service.deleted_movements["category"] == "transporte"
        assert service.deleted_movements["card_id"] is None
        assert "3" in result

    async def test_delete_movements_by_date_range(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction()]
        toolkit = TransactionToolkit(service, cards=FakeCardService())

        await toolkit.dispatch(
            DELETE_BY_FILTER_TOOL,
            {"start_date": "2026-07-05", "end_date": "2026-07-20"},
            user_id="u1",
        )

        assert service.deleted_movements["period_start"] == date(2026, 7, 5)
        assert service.deleted_movements["period_end"] == date(2026, 7, 20)

    async def test_delete_movements_unknown_card(self) -> None:
        toolkit = TransactionToolkit(FakeTransactionService(), cards=FakeCardService(cards=[]))

        result = await toolkit.dispatch(
            DELETE_BY_FILTER_TOOL, {"card_name": "Nu", "period": "2026-08"}, user_id="u1"
        )

        assert "no encontré" in result.lower()

    async def test_delete_movements_requires_time_scope(self) -> None:
        # Destructive: without a period/range it must ASK, never wipe all history.
        service = FakeTransactionService()
        service.items = [_transaction()]
        toolkit = TransactionToolkit(service, cards=FakeCardService())

        result = await toolkit.dispatch(
            DELETE_BY_FILTER_TOOL, {"card_name": "Visa BBVA"}, user_id="u1"
        )

        assert "período" in result.lower() or "periodo" in result.lower()
        assert not hasattr(service, "deleted_movements")  # nothing was deleted

    async def test_delete_partial_date_range_asks(self) -> None:
        service = FakeTransactionService()
        service.items = [_transaction()]
        toolkit = TransactionToolkit(service, cards=FakeCardService())

        result = await toolkit.dispatch(
            DELETE_BY_FILTER_TOOL, {"start_date": "2026-07-05"}, user_id="u1"
        )

        assert "ambas" in result.lower() or "fin" in result.lower()
        assert not hasattr(service, "deleted_movements")
