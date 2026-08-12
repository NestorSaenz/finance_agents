"""Goal use cases (business logic), including progress and contributions."""

from datetime import UTC, date, datetime
from decimal import Decimal

from app.core.exceptions import (
    GoalNotFoundError,
    GoalWithdrawalExceedsBalanceError,
    InvalidAmountError,
)
from app.core.logging import get_logger
from app.shared.serialization import decimal_to_db
from app.shared.types import GoalId, GoalStatus, UserId

from ..interfaces import (
    GoalContributionRepositoryABC,
    GoalRepositoryABC,
    GoalServiceABC,
)
from ..models import (
    Goal,
    GoalContribution,
    GoalContributionView,
    GoalCreate,
    GoalProgress,
)

logger = get_logger(__name__)


class GoalService(GoalServiceABC):
    """Orchestrates goal persistence, contributions, and progress evaluation."""

    def __init__(
        self,
        repository: GoalRepositoryABC,
        contributions: GoalContributionRepositoryABC,
    ) -> None:
        self._repository = repository
        self._contributions = contributions

    async def create_goal(self, goal: GoalCreate, user_id: UserId) -> Goal:
        return await self._repository.create(goal, user_id)

    async def get_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        goal = await self._repository.get_by_id(goal_id, user_id)
        if goal is None:
            raise GoalNotFoundError(goal_id)
        return goal

    async def list_goals(
        self,
        user_id: UserId,
        *,
        page: int,
        page_size: int,
        as_of: date | None = None,
    ) -> tuple[list[Goal], int]:
        offset = (page - 1) * page_size
        items = await self._repository.list_page(user_id, limit=page_size, offset=offset)
        total = await self._repository.count(user_id)
        if as_of is None:
            return items, total
        # Rebuild each goal's progress AT the month-end from its dated
        # contributions (one fetch, grouped in Python), so a month shows only
        # what had been saved by then instead of the running cached total.
        sums = await self._contributions.sums_up_to(user_id, as_of)
        return [_with_cumulative(goal, sums.get(goal.id, Decimal("0"))) for goal in items], total

    async def contribute(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date | None = None,
    ) -> Goal:
        # A completed goal can still receive contributions: you may save beyond
        # the target, and dated back-contributions are needed to build per-month
        # history. So we record the contribution regardless of status.
        goal = await self.get_goal(goal_id, user_id)

        await self._contributions.create(
            goal_id, user_id, amount, contribution_date or _today()
        )

        # Keep ``current_amount`` as a cached running total so unfiltered reads
        # stay cheap; the dated contribution above is the source of truth for
        # per-month progress.
        new_amount = goal.current_amount + amount
        data: dict[str, object] = {"current_amount": decimal_to_db(new_amount)}
        if new_amount >= goal.target_amount:
            data["status"] = GoalStatus.COMPLETED.value
            logger.info("Goal reached", goal_id=goal_id)

        return await self._repository.update(goal_id, user_id, data)

    async def withdraw_from_goal(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        withdrawal_date: date,
    ) -> Goal:
        if amount <= 0:
            raise InvalidAmountError(
                float(amount), "Withdrawal amount must be positive"
            )
        goal = await self.get_goal(goal_id, user_id)  # existence/ownership check
        if amount > goal.current_amount:
            raise GoalWithdrawalExceedsBalanceError(goal.name, goal.current_amount)

        # A withdrawal is a NEGATIVE contribution: it rewinds progress (mirroring
        # ``contribute``, which writes a positive one) and, since aportes are
        # netted out of disponible, the money returns there — no income/expense.
        await self._contributions.create(goal_id, user_id, -amount, withdrawal_date)

        # Roll back the cached running total and re-derive completion, mirroring
        # ``update_goal``: only ACTIVE/COMPLETED is derived; paused/cancelled stay.
        # ``new_amount`` can't go below 0 given the balance check above.
        new_amount = goal.current_amount - amount
        data: dict[str, object] = {"current_amount": decimal_to_db(new_amount)}
        if goal.status in (GoalStatus.ACTIVE, GoalStatus.COMPLETED):
            reached = new_amount >= goal.target_amount
            data["status"] = (
                GoalStatus.COMPLETED if reached else GoalStatus.ACTIVE
            ).value
        logger.info("Goal withdrawal", goal_id=goal_id, user_id=user_id)
        return await self._repository.update(goal_id, user_id, data)

    async def contributed_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> Decimal:
        return await self._contributions.sum_in_period(user_id, period_start, period_end)

    async def list_contributions_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[GoalContributionView]:
        # Mirror ``CreditCardService.list_payments``: pull the dated contributions
        # (already newest-first) and resolve each goal's name. A contribution whose
        # goal was deleted falls back to "Meta".
        contributions = await self._contributions.list_in_period(
            user_id, period_start, period_end
        )
        total = await self._repository.count(user_id)
        goals = await self._repository.list_page(user_id, limit=max(total, 1), offset=0)
        names = {g.id: g.name for g in goals}
        return [
            GoalContributionView(
                goal_name=names.get(c.goal_id, "Meta"),
                amount=c.amount,
                contribution_date=c.contribution_date,
            )
            for c in contributions
        ]

    async def update_goal(
        self,
        goal_id: GoalId,
        user_id: UserId,
        *,
        name: str | None = None,
        target_amount: Decimal | None = None,
        target_date: date | None = None,
    ) -> Goal:
        goal = await self.get_goal(goal_id, user_id)  # existence/ownership check
        data: dict[str, object] = {}
        if name is not None:
            data["name"] = name
        if target_amount is not None:
            data["target_amount"] = decimal_to_db(target_amount)
            # Re-evaluate completion against the NEW target: raising it can reopen
            # a completed goal; lowering it can complete an active one. Paused/
            # cancelled goals keep their status (only ACTIVE/COMPLETED is derived).
            if goal.status in (GoalStatus.ACTIVE, GoalStatus.COMPLETED):
                reached = goal.current_amount >= target_amount
                data["status"] = (
                    GoalStatus.COMPLETED if reached else GoalStatus.ACTIVE
                ).value
        if target_date is not None:
            data["target_date"] = target_date.isoformat()
        if not data:
            return goal
        return await self._repository.update(goal_id, user_id, data)

    async def delete_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        # Fetch first to confirm existence/ownership and return what was removed.
        goal = await self.get_goal(goal_id, user_id)
        await self._repository.delete(goal_id, user_id)
        logger.info("Goal deleted", goal_id=goal_id, user_id=user_id)
        return goal

    async def remove_contribution(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date | None = None,
    ) -> Goal | None:
        goal = await self.get_goal(goal_id, user_id)  # existence/ownership check
        contribs = await self._contributions.list_for_goal(user_id, goal_id)

        # Match on amount (and date when given). ``list_for_goal`` is already
        # newest-first, so the first match is the most recent — the one to undo.
        match = next(
            (
                c
                for c in contribs
                if c.amount == amount
                and (contribution_date is None or c.contribution_date == contribution_date)
            ),
            None,
        )
        if match is None:
            return None

        await self._contributions.delete(match.id, user_id)

        # Roll back the cached running total and re-derive completion, mirroring
        # ``update_goal``: only ACTIVE/COMPLETED is derived; paused/cancelled stay.
        new_amount = max(goal.current_amount - amount, Decimal("0"))
        data: dict[str, object] = {"current_amount": decimal_to_db(new_amount)}
        if goal.status in (GoalStatus.ACTIVE, GoalStatus.COMPLETED):
            reached = new_amount >= goal.target_amount
            data["status"] = (
                GoalStatus.COMPLETED if reached else GoalStatus.ACTIVE
            ).value
        logger.info("Goal contribution removed", goal_id=goal_id, user_id=user_id)
        return await self._repository.update(goal_id, user_id, data)

    async def get_progress(
        self, goal_id: GoalId, user_id: UserId, as_of: date | None = None
    ) -> GoalProgress:
        goal = await self.get_goal(goal_id, user_id)
        return _build_progress(goal, as_of or _today())

    async def list_contributions(
        self, goal_id: GoalId, user_id: UserId
    ) -> list[GoalContribution]:
        await self.get_goal(goal_id, user_id)  # existence/ownership check
        return await self._contributions.list_for_goal(user_id, goal_id)


def _with_cumulative(goal: Goal, cumulative: Decimal) -> Goal:
    """Return a copy of ``goal`` whose amount/status reflect the month's cumulative.

    A goal counts as completed for the month only if its cumulative reached the
    target by then; otherwise it's active, even when the cached running total had
    already completed it in a later month. Non-completion statuses (paused,
    cancelled) are preserved — only COMPLETED is (re)derived from the cumulative.
    """
    if goal.status in (GoalStatus.ACTIVE, GoalStatus.COMPLETED):
        status = (
            GoalStatus.COMPLETED
            if cumulative >= goal.target_amount
            else GoalStatus.ACTIVE
        )
    else:
        status = goal.status  # paused / cancelled stay as-is
    return goal.model_copy(update={"current_amount": cumulative, "status": status})


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
