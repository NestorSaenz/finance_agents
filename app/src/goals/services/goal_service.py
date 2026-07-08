"""Goal use cases (business logic), including progress and contributions."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.exceptions import GoalAlreadyCompletedError, GoalNotFoundError
from app.core.logging import get_logger
from app.shared.serialization import decimal_to_db
from app.shared.types import GoalId, GoalStatus, UserId

from ..interfaces import GoalRepositoryABC, GoalServiceABC
from ..models import Goal, GoalCreate, GoalProgress

logger = get_logger(__name__)


class GoalService(GoalServiceABC):
    """Orchestrates goal persistence, contributions, and progress evaluation."""

    def __init__(self, repository: GoalRepositoryABC) -> None:
        self._repository = repository

    async def create_goal(self, goal: GoalCreate, user_id: UserId) -> Goal:
        return await self._repository.create(goal, user_id)

    async def get_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        goal = await self._repository.get_by_id(goal_id, user_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        return goal

    async def list_goals(
        self, user_id: UserId, *, page: int, page_size: int
    ) -> tuple[list[Goal], int]:
        offset = (page - 1) * page_size
        items = await self._repository.list_page(user_id, limit=page_size, offset=offset)
        total = await self._repository.count(user_id)
        return items, total

    async def contribute(self, goal_id: GoalId, user_id: UserId, amount: Decimal) -> Goal:
        goal = await self.get_goal(goal_id, user_id)
        if goal.status == GoalStatus.COMPLETED:
            raise GoalAlreadyCompletedError(goal.id, goal.name)

        new_amount = goal.current_amount + amount
        data: dict[str, object] = {"current_amount": decimal_to_db(new_amount)}
        if new_amount >= goal.target_amount:
            data["status"] = GoalStatus.COMPLETED.value
            logger.info("Goal reached", goal_id=goal_id)

        return await self._repository.update(goal_id, user_id, data)

    async def delete_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        # Fetch first to confirm existence/ownership and return what was removed.
        goal = await self.get_goal(goal_id, user_id)
        await self._repository.delete(goal_id, user_id)
        logger.info("Goal deleted", goal_id=goal_id, user_id=user_id)
        return goal

    async def get_progress(
        self, goal_id: GoalId, user_id: UserId, as_of: date | None = None
    ) -> GoalProgress:
        goal = await self.get_goal(goal_id, user_id)
        return _build_progress(goal, as_of or _today())


def _build_progress(goal: Goal, reference: date) -> GoalProgress:
    target = goal.target_amount
    current = goal.current_amount
    remaining = max(target - current, Decimal("0"))
    percentage = float(current / target * 100) if target > 0 else 0.0
    is_completed = goal.status == GoalStatus.COMPLETED or current >= target

    months_remaining = (
        _months_between(reference, goal.target_date) if goal.target_date else None
    )
    required = _required_monthly(remaining, months_remaining)
    on_track = is_completed or goal.target_date is None or reference <= goal.target_date

    return GoalProgress(
        goal=goal,
        percentage=round(percentage, 2),
        remaining=remaining,
        is_completed=is_completed,
        months_remaining=months_remaining,
        required_monthly_contribution=required,
        on_track=on_track,
    )


def _months_between(reference: date, target_date: date) -> int:
    """Whole months from ``reference`` to ``target_date`` (never negative)."""
    months = (target_date.year - reference.year) * 12 + (target_date.month - reference.month)
    return max(months, 0)


def _required_monthly(remaining: Decimal, months_remaining: int | None) -> Decimal | None:
    """Monthly amount needed to reach the goal.

    None when there is no deadline; the full remaining amount when the deadline
    has passed (0 months); otherwise the remaining spread across the months.
    """
    if remaining <= 0:
        return Decimal("0")
    if months_remaining is None:
        return None
    if months_remaining <= 0:
        return remaining
    return (remaining / Decimal(months_remaining)).quantize(Decimal("0.01"))


def _today() -> date:
    return datetime.now(UTC).date()
