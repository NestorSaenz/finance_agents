"""Transaction use cases (business logic)."""

from datetime import date
from decimal import Decimal

from app.core.exceptions import TransactionNotFoundError
from app.core.logging import get_logger
from app.shared.serialization import decimal_to_db
from app.shared.types import (
    Category,
    PaymentMethod,
    TransactionId,
    TransactionType,
    UserId,
)

from ..constants import SUMMARY_FETCH_LIMIT
from ..interfaces import (
    TransactionCategorizerABC,
    TransactionRepositoryABC,
    TransactionServiceABC,
)
from ..models import CategorySpending, SpendingSummary, Transaction, TransactionCreate

logger = get_logger(__name__)


class TransactionService(TransactionServiceABC):
    """Orchestrates transaction persistence and auto-categorization."""

    def __init__(
        self,
        repository: TransactionRepositoryABC,
        categorizer: TransactionCategorizerABC,
    ) -> None:
        self._repository = repository
        self._categorizer = categorizer

    async def create_transaction(
        self, transaction: TransactionCreate, user_id: UserId
    ) -> Transaction:
        if transaction.category is None:
            category = await self._categorizer.categorize(transaction.description)
            transaction = transaction.model_copy(update={"category": category})
            logger.info("Transaction auto-categorized", category=category)

        return await self._repository.create(transaction, user_id)

    async def get_transaction(
        self, transaction_id: TransactionId, user_id: UserId
    ) -> Transaction:
        transaction = await self._repository.get_by_id(transaction_id, user_id)
        if transaction is None:
            raise TransactionNotFoundError(transaction_id)
        return transaction

    async def list_transactions(
        self,
        user_id: UserId,
        *,
        page: int,
        page_size: int,
        transaction_type: TransactionType | None = None,
        category: Category | None = None,
    ) -> tuple[list[Transaction], int]:
        offset = (page - 1) * page_size
        items = await self._repository.list_page(
            user_id,
            limit=page_size,
            offset=offset,
            transaction_type=transaction_type,
            category=category,
        )
        total = await self._repository.count(
            user_id,
            transaction_type=transaction_type,
            category=category,
        )
        return items, total

    async def update_transaction(
        self,
        transaction_id: TransactionId,
        user_id: UserId,
        *,
        amount: Decimal | None = None,
        description: str | None = None,
        category: Category | None = None,
        transaction_type: TransactionType | None = None,
        transaction_date: date | None = None,
        payment_method: PaymentMethod | None = None,
    ) -> Transaction:
        # Ensure it exists and belongs to the user before touching it.
        await self.get_transaction(transaction_id, user_id)

        data: dict[str, object] = {}
        if amount is not None:
            data["amount"] = decimal_to_db(amount)
        if description is not None:
            data["description"] = description
        if category is not None:
            data["category"] = category
        if transaction_type is not None:
            data["type"] = transaction_type.value
        if transaction_date is not None:
            data["transaction_date"] = transaction_date.isoformat()
        if payment_method is not None:
            data["payment_method"] = payment_method.value

        if not data:
            return await self.get_transaction(transaction_id, user_id)

        updated = await self._repository.update(transaction_id, user_id, data)
        logger.info("Transaction updated", transaction_id=transaction_id, user_id=user_id)
        return updated

    async def delete_transaction(
        self, transaction_id: TransactionId, user_id: UserId
    ) -> Transaction:
        # Fetch first so we can confirm existence/ownership and return what was removed.
        transaction = await self.get_transaction(transaction_id, user_id)
        await self._repository.delete(transaction_id, user_id)
        logger.info("Transaction deleted", transaction_id=transaction_id, user_id=user_id)
        return transaction

    async def get_spending_summary(
        self, user_id: UserId, *, period_start: date, period_end: date
    ) -> SpendingSummary:
        # Fetch a wide page and aggregate in-period (money stays Decimal).
        items = await self._repository.list_page(
            user_id, limit=SUMMARY_FETCH_LIMIT, offset=0
        )
        in_period = [t for t in items if period_start <= t.transaction_date <= period_end]

        income = sum(
            (t.amount for t in in_period if t.transaction_type == TransactionType.INCOME),
            Decimal("0"),
        )
        by_category: dict[Category, Decimal] = {}
        for t in in_period:
            if t.transaction_type == TransactionType.EXPENSE:
                by_category[t.category] = by_category.get(t.category, Decimal("0")) + t.amount

        expenses = sum(by_category.values(), Decimal("0"))
        categories = [
            CategorySpending(category=cat, amount=amount)
            for cat, amount in sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
        ]
        credit = sum(
            (
                t.amount
                for t in in_period
                if t.transaction_type == TransactionType.EXPENSE
                and t.payment_method == PaymentMethod.CREDITO
            ),
            Decimal("0"),
        )
        cash = sum(
            (
                t.amount
                for t in in_period
                if t.transaction_type == TransactionType.EXPENSE
                and t.payment_method == PaymentMethod.EFECTIVO
            ),
            Decimal("0"),
        )
        return SpendingSummary(
            total_income=income,
            total_expenses=expenses,
            by_category=categories,
            credit_expenses=credit,
            cash_expenses=cash,
        )
