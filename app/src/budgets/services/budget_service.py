"""Budget use cases (business logic), including alert evaluation."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.exceptions import BudgetNotFoundError
from app.core.logging import get_logger
from app.shared.types import BudgetId, UserId, normalize_category

from ..interfaces import BudgetRepositoryABC, BudgetServiceABC, BudgetSpendingABC
from ..models import Budget, BudgetCreate, BudgetStatus
from ..period import compute_period

logger = get_logger(__name__)


class BudgetService(BudgetServiceABC):
    """Orchestrates budget persistence and spending/alert evaluation."""

    def __init__(
        self,
        repository: BudgetRepositoryABC,
        spending: BudgetSpendingABC,
    ) -> None:
        self._repository = repository
        self._spending = spending

    async def create_budget(self, budget: BudgetCreate, user_id: UserId) -> Budget:
        return await self._repository.create(budget, user_id)

    async def get_budget(self, budget_id: BudgetId, user_id: UserId) -> Budget:
        budget = await self._repository.get_by_id(budget_id, user_id)
        if budget is None:
            raise BudgetNotFoundError(budget_id)
        return budget

    async def list_budgets(
        self, user_id: UserId, *, page: int, page_size: int
    ) -> tuple[list[Budget], int]:
        offset = (page - 1) * page_size
        items = await self._repository.list_page(user_id, limit=page_size, offset=offset)
        total = await self._repository.count(user_id)
        return items, total

    async def get_budget_status(
        self, budget_id: BudgetId, user_id: UserId, as_of: date | None = None
    ) -> BudgetStatus:
        budget = await self.get_budget(budget_id, user_id)
        return await self._build_status(budget, as_of or _today())

    async def get_active_alerts(
        self, user_id: UserId, as_of: date | None = None
    ) -> list[BudgetStatus]:
        statuses = await self.get_all_status(user_id, as_of)
        return [status for status in statuses if status.alert_triggered]

    async def get_all_status(
        self, user_id: UserId, as_of: date | None = None
    ) -> list[BudgetStatus]:
        reference = as_of or _today()
        budgets = await self._repository.list_active(user_id)
        return [await self._build_status(b, reference) for b in budgets]

    async def update_budget(
        self,
        budget_id: BudgetId,
        user_id: UserId,
        *,
        name: str | None = None,
        amount: Decimal | None = None,
    ) -> Budget:
        updated = await self._repository.update(
            budget_id, user_id, name=name, amount=amount
        )
        if updated is None:
            raise BudgetNotFoundError(budget_id)
        return updated

    async def delete_budget(self, budget_id: BudgetId, user_id: UserId) -> Budget:
        deleted = await self._repository.delete(budget_id, user_id)
        if deleted is None:
            raise BudgetNotFoundError(budget_id)
        return deleted

    async def resolve_budget(self, reference: str, user_id: UserId) -> Budget | None:
        """Find a budget by exact name, then category, then fuzzy name.

        The LLM references a budget by what the user says ("alimentación"), never
        by id; among ambiguous matches the first active budget wins.
        """
        target = reference.lower().strip()
        if not target:
            return None
        budgets = await self._repository.list_active(user_id)
        return (
            next((b for b in budgets if b.name.lower() == target), None)
            or next((b for b in budgets if b.category and b.category == target), None)
            or next(
                (b for b in budgets if target in b.name.lower() or b.name.lower() in target),
                None,
            )
        )

    async def recategorize(self, user_id: UserId, old: str, new: str) -> int:
        old_norm, new_norm = normalize_category(old), normalize_category(new)
        if old_norm == new_norm:
            return 0
        # If the target category already has a tope, relabeling would leave TWO
        # budget rows for one category (resolve_budget/get_all_status would pick or
        # double-count them). Merge by deleting the source tope, keeping the target.
        active = await self._repository.list_active(user_id)
        if any((b.category or "") == new_norm for b in active):
            return await self._repository.delete_by_category(user_id, old_norm)
        return await self._repository.recategorize(user_id, old_norm, new_norm)

    async def delete_by_category(self, user_id: UserId, category: str) -> int:
        return await self._repository.delete_by_category(
            user_id, normalize_category(category)
        )

    async def _build_status(self, budget: Budget, reference: date) -> BudgetStatus:
        period_start, period_end = compute_period(budget.period_type, reference)
        spent = await self._spending.get_spent(
            budget.user_id, budget.category, period_start, period_end
        )

        # Compute the ratio and the alert decision in Decimal (exact at the
        # threshold boundary); expose percentage as float for the response model.
        percentage = spent / budget.amount * 100 if budget.amount > 0 else Decimal("0")
        alert_triggered = budget.alert_enabled and percentage >= budget.alert_threshold

        return BudgetStatus(
            budget=budget,
            period_start=period_start,
            period_end=period_end,
            spent=spent,
            remaining=budget.amount - spent,
            percentage=round(float(percentage), 2),
            alert_triggered=alert_triggered,
        )


def _today() -> date:
    return datetime.now(UTC).date()
