"""Transaction use cases (business logic)."""

import asyncio
import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

from app.core.exceptions import TransactionNotFoundError
from app.core.logging import get_logger
from app.shared.serialization import decimal_to_db
from app.shared.types import (
    CardId,
    Category,
    PaymentMethod,
    TransactionId,
    TransactionType,
    UserId,
    normalize_category,
)

from ..constants import (
    CATEGORY_FUZZY_MATCH_CUTOFF,
    DELETE_CONCURRENCY,
    SUMMARY_FETCH_LIMIT,
)
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

    async def create_installments(
        self, base: TransactionCreate, installments: int, user_id: UserId
    ) -> list[Transaction]:
        """Split a deferred purchase into ``installments`` monthly transactions.

        The total (``base.amount``) is divided across the installments — the first
        dated at ``base.transaction_date`` and each next one a month later — so a
        household budget sees the per-month cost, not the full amount up front. The
        last installment absorbs any rounding remainder so the parts sum exactly to
        the total. The category is resolved once and shared across the installments.
        """
        if installments < 2:
            return [await self.create_transaction(base, user_id)]

        if base.category is None:
            category = await self._categorizer.categorize(base.description)
            base = base.model_copy(update={"category": category})
            logger.info("Installment purchase auto-categorized", category=category)

        # Each installment is its own insert; the project has no unit-of-work, so a
        # mid-way failure could leave a partial split. Acceptable here (single-user
        # home use, reliable inserts); a proper DB transaction would be the fix.
        amounts = _split_amount(base.amount, installments)
        created = [
            await self._repository.create(
                base.model_copy(
                    update={
                        "amount": amount,
                        "description": f"{base.description} (cuota {index + 1}/{installments})",
                        "transaction_date": _add_months(base.transaction_date, index),
                        # Reset so each installment's budget month is its own date,
                        # not the whole purchase's first-statement date (each cuota
                        # is already spread month by month).
                        "budget_date": None,
                    }
                ),
                user_id,
            )
            for index, amount in enumerate(amounts)
        ]
        logger.info("Installments registered", installments=installments, user_id=user_id)
        return created

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
        card_id: CardId | None = None,
    ) -> tuple[list[Transaction], int]:
        offset = (page - 1) * page_size
        items = await self._repository.list_page(
            user_id,
            limit=page_size,
            offset=offset,
            transaction_type=transaction_type,
            category=category,
            card_id=card_id,
        )
        total = await self._repository.count(
            user_id,
            transaction_type=transaction_type,
            category=category,
            card_id=card_id,
        )
        return items, total

    async def resolve_category(self, proposed: Category, user_id: UserId) -> Category:
        normalized = normalize_category(proposed)
        existing = await self._user_categories(user_id)
        return _match_category(normalized, existing)

    async def list_categories(self, user_id: UserId) -> list[Category]:
        return await self._user_categories(user_id)

    async def count_by_category(self, user_id: UserId, category: Category) -> int:
        return await self._repository.count(
            user_id, category=normalize_category(category)
        )

    async def recategorize(self, user_id: UserId, old: Category, new: Category) -> int:
        old_norm, new_norm = normalize_category(old), normalize_category(new)
        if old_norm == new_norm:
            return 0
        return await self._repository.recategorize(user_id, old_norm, new_norm)

    async def delete_by_category(self, user_id: UserId, category: Category) -> int:
        return await self._repository.delete_by_category(
            user_id, normalize_category(category)
        )

    async def _user_categories(self, user_id: UserId) -> list[str]:
        """Distinct categories the user has used (most-recent first, deduped).

        Deliberately reuses the wide ``list_page`` fetch (same cap as the summary)
        rather than a dedicated DISTINCT query: personal-finance volumes are small
        and the fuzzy match runs over the tiny deduped set. Revisit with a repo-level
        distinct query only if this ever lands on a hot path.
        """
        items = await self._repository.list_page(
            user_id, limit=SUMMARY_FETCH_LIMIT, offset=0
        )
        # dict preserves first-seen order; list_page returns newest first.
        return list(dict.fromkeys(t.category for t in items if t.category))

    async def list_by_period(
        self,
        user_id: UserId,
        *,
        period_start: date,
        period_end: date,
        transaction_type: TransactionType | None = None,
        category: Category | None = None,
        card_id: CardId | None = None,
    ) -> list[Transaction]:
        # Push type/category to the repo (equality filters it supports) so a
        # filtered query doesn't miss older matches beyond the fetch window, then
        # filter the date range in-memory (the repo has no range filter). Capped
        # at SUMMARY_FETCH_LIMIT, newest first — enough for personal-finance use.
        items = await self._repository.list_page(
            user_id,
            limit=SUMMARY_FETCH_LIMIT,
            offset=0,
            transaction_type=transaction_type,
            category=category,
            card_id=card_id,
        )
        in_period = [
            t for t in items if period_start <= t.transaction_date <= period_end
        ]
        in_period.sort(key=lambda t: (t.transaction_date, t.created_at), reverse=True)
        return in_period

    async def delete_movements(
        self,
        user_id: UserId,
        *,
        card_id: CardId | None = None,
        category: Category | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> int:
        """Delete transactions matching the given filters (ANDed); rows deleted.

        Filters: card, category, and/or a ``[period_start, period_end]`` date
        range. The DB client has no range delete, so matching rows are fetched
        (card/category pushed down as equality filters) and deleted by id with
        bounded concurrency — cheap at personal-finance volumes.

        At least one filter is required: deleting with no filter at all would wipe
        the user's whole history, so it raises instead.
        """
        has_range = period_start is not None and period_end is not None
        if card_id is None and category is None and not has_range:
            raise ValueError(
                "delete_movements needs at least a card, category or date range"
            )
        items = await self._repository.list_page(
            user_id,
            limit=SUMMARY_FETCH_LIMIT,
            offset=0,
            category=normalize_category(category) if category else None,
            card_id=card_id,
        )
        if period_start is not None and period_end is not None:
            items = [
                t for t in items if period_start <= t.transaction_date <= period_end
            ]

        # Cap fan-out so an all-history delete can't open hundreds of connections.
        semaphore = asyncio.Semaphore(DELETE_CONCURRENCY)

        async def _delete_one(transaction_id: TransactionId) -> None:
            async with semaphore:
                await self._repository.delete(transaction_id, user_id)

        await asyncio.gather(*(_delete_one(t.id) for t in items))
        return len(items)

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


def _split_amount(total: Decimal, parts: int) -> list[Decimal]:
    """Split ``total`` into ``parts`` amounts; the last absorbs the remainder.

    Guarantees the parts sum exactly to ``total`` (no pesos lost to rounding).
    """
    each = (total / parts).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return [each] * (parts - 1) + [total - each * (parts - 1)]


def _add_months(reference: date, months: int) -> date:
    """Return ``reference`` advanced by ``months``, clamping the day to month length."""
    absolute = reference.month - 1 + months
    year = reference.year + absolute // 12
    month = absolute % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(reference.day, last_day))


def _match_category(proposed: str, existing: list[str]) -> str:
    """Return an existing category equal or highly similar to ``proposed``.

    Exact match reuses the stored spelling; otherwise the closest existing
    category is reused only when the similarity clears the (high) cutoff, so a
    typo snaps to the real category but distinct categories never collapse. Falls
    back to ``proposed`` when nothing is close (a genuinely new category).
    """
    target = proposed.strip().lower()
    if not target:
        return proposed
    for category in existing:
        if category.lower() == target:
            return category
    best, best_ratio = "", 0.0
    for category in existing:
        ratio = SequenceMatcher(None, target, category.lower()).ratio()
        if ratio > best_ratio:
            best, best_ratio = category, ratio
    return best if best_ratio >= CATEGORY_FUZZY_MATCH_CUTOFF else proposed
