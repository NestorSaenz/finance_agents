"""Goal use cases (business logic), including progress and contributions."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from itertools import accumulate

from app.core.config import settings
from app.core.exceptions import (
    GoalNotFoundError,
    GoalWithdrawalExceedsBalanceError,
    InvalidAmountError,
    InvalidPlanPeriodError,
)
from app.core.logging import get_logger
from app.shared.clock import current_today
from app.shared.serialization import decimal_to_db
from app.shared.types import (
    GoalId,
    GoalPlanClearMode,
    GoalPlanKind,
    GoalPlanScope,
    GoalStatus,
    UserId,
)

from ..constants import (
    DEFAULT_HISTORY_MONTHS,
    MAX_HISTORY_MONTHS,
    MAX_PLANNED_AMOUNT,
    PLAN_AMOUNT_QUANTUM,
)
from ..interfaces import (
    ContributionMonthsProviderABC,
    GoalContributionRepositoryABC,
    GoalPlanRepositoryABC,
    GoalRepositoryABC,
    GoalServiceABC,
)
from ..models import (
    Goal,
    GoalContribution,
    GoalContributionView,
    GoalCreate,
    GoalMonthContribution,
    GoalMonthLine,
    GoalPlan,
    GoalPlanStatus,
    GoalProgress,
)
from ..planning import (
    add_months,
    first_of_month,
    goal_created_month,
    last_of_month,
    month_range,
    resolve_plan,
)

logger = get_logger(__name__)


class GoalService(GoalServiceABC):
    """Orchestrates goal persistence, contributions, and progress evaluation."""

    def __init__(
        self,
        repository: GoalRepositoryABC,
        contributions: GoalContributionRepositoryABC,
        plans: GoalPlanRepositoryABC,
        months: ContributionMonthsProviderABC,
    ) -> None:
        self._repository = repository
        self._contributions = contributions
        self._plans = plans
        self._months = months

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
            goal_id, user_id, amount, contribution_date or current_today()
        )

        # Recompute ``current_amount`` from the ledger (never ``current ± amount``)
        # so the cache can NEVER drift from ``sum(contributions)``: any prior
        # divergence is self-healed here. The dated contribution above remains the
        # source of truth for per-month progress.
        return await self._recompute_cache(goal, user_id)

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
        # Validate against the LEDGER balance (sum of contributions), never the
        # cached ``current_amount`` which could have drifted: you cannot take out
        # more than the ledger actually holds.
        balance = await self._contributions.sum_for_goal(user_id, goal_id)
        if amount > balance:
            raise GoalWithdrawalExceedsBalanceError(goal.name, balance)

        # A withdrawal is a NEGATIVE contribution: it rewinds progress (mirroring
        # ``contribute``, which writes a positive one) and, since aportes are
        # netted out of disponible, the money returns there — no income/expense.
        await self._contributions.create(goal_id, user_id, -amount, withdrawal_date)

        logger.info("Goal withdrawal", goal_id=goal_id, user_id=user_id)
        # Recompute the cache from the ledger and re-derive completion.
        return await self._recompute_cache(goal, user_id)

    async def set_goal_amount(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        on_date: date,
    ) -> Goal:
        if amount < 0:
            raise InvalidAmountError(
                float(amount), "Goal amount must be zero or positive"
            )
        goal = await self.get_goal(goal_id, user_id)  # existence/ownership check
        balance = await self._contributions.sum_for_goal(user_id, goal_id)

        if amount > balance:
            # Real money in: record only the delta as a contribution so the ledger
            # (and the dashboard's cash-flow) reflects exactly what was added.
            return await self.contribute(goal_id, user_id, amount - balance, on_date)
        if amount < balance:
            # Real money out: withdraw the delta (a negative contribution).
            return await self.withdraw_from_goal(
                goal_id, user_id, balance - amount, on_date
            )

        # amount == balance: PURE RECONCILE — the ledger already sums to ``amount``,
        # so snap the cache to it and write NO ledger row (zero cash-flow impact).
        # This also covers "déjalo en 0" when the ledger balance is 0.
        logger.info("Goal amount reconciled", goal_id=goal_id, user_id=user_id)
        data: dict[str, object] = {"current_amount": decimal_to_db(amount)}
        status = _status_after(goal, amount)
        if status is not None:
            data["status"] = status
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

        logger.info("Goal contribution removed", goal_id=goal_id, user_id=user_id)
        # Recompute the cache straight from the ledger (no ``max(..., 0)`` floor,
        # which masked drift) and re-derive completion.
        return await self._recompute_cache(goal, user_id)

    async def set_paused(
        self, goal_id: GoalId, user_id: UserId, paused: bool
    ) -> Goal:
        goal = await self.get_goal(goal_id, user_id)  # existence/ownership check
        if paused:
            new_status = GoalStatus.PAUSED
        elif goal.status == GoalStatus.PAUSED:
            # Resume: re-derive active vs completed from the saved amount, so a
            # goal that hit its target while paused comes back as COMPLETED.
            new_status = (
                GoalStatus.COMPLETED
                if goal.current_amount >= goal.target_amount
                else GoalStatus.ACTIVE
            )
        else:
            # Resuming a goal that isn't paused is a no-op; never reactivate a
            # terminal status (e.g. a cancelled goal) by re-deriving it.
            return goal
        logger.info(
            "Goal pause toggled", goal_id=goal_id, user_id=user_id, paused=paused
        )
        return await self._repository.update(
            goal_id, user_id, {"status": new_status.value}
        )

    async def set_plan(
        self,
        user_id: UserId,
        goal_id: GoalId,
        amount: Decimal,
        month: date,
        scope: GoalPlanScope,
    ) -> Decimal | None:
        planned = _validated_plan_amount(amount)
        goal = await self.get_goal(goal_id, user_id)  # existence/ownership check
        target = first_of_month(month)
        _ensure_not_before_creation(goal, target)

        if scope == GoalPlanScope.DESDE_MES:
            # "From this month on" replaces what was planned ahead: later recurrings
            # would otherwise keep winning, and this month's override would shadow the
            # new one. Later overrides are specific months and stay. Delete first so a
            # failed write leaves the previous plan intact.
            rows = await self._plans.list_for_goal(user_id, goal_id)
            await self._delete_rows(
                user_id,
                [
                    p
                    for p in rows
                    if (p.kind == GoalPlanKind.RECURRING and p.month > target)
                    or (p.kind == GoalPlanKind.OVERRIDE and p.month == target)
                ],
            )
            await self._plans.upsert(user_id, goal_id, target, GoalPlanKind.RECURRING, planned)
        else:
            await self._plans.upsert(user_id, goal_id, target, GoalPlanKind.OVERRIDE, planned)

        logger.info("Goal plan set", goal_id=goal_id, user_id=user_id, scope=scope.value)
        return await self._plan_for_month(goal, user_id, target)

    async def clear_plan(
        self,
        user_id: UserId,
        goal_id: GoalId,
        month: date,
        mode: GoalPlanClearMode,
    ) -> Decimal | None:
        goal = await self.get_goal(goal_id, user_id)  # existence/ownership check
        target = first_of_month(month)
        _ensure_not_before_creation(goal, target)

        if mode == GoalPlanClearMode.SIN_PLAN:
            await self._plans.upsert(
                user_id, goal_id, target, GoalPlanKind.OVERRIDE, Decimal("0")
            )
        elif mode == GoalPlanClearMode.TERMINAR:
            # Stop planning from this month on: nothing planned ahead may survive.
            rows = await self._plans.list_for_goal(user_id, goal_id)
            await self._delete_rows(
                user_id,
                [
                    p
                    for p in rows
                    if (p.kind == GoalPlanKind.RECURRING and p.month > target)
                    or (p.kind == GoalPlanKind.OVERRIDE and p.month >= target)
                ],
            )
            await self._plans.upsert(
                user_id, goal_id, target, GoalPlanKind.RECURRING, Decimal("0")
            )
        else:  # VOLVER_AL_GENERAL
            await self._plans.delete(user_id, goal_id, target, GoalPlanKind.OVERRIDE)

        logger.info("Goal plan cleared", goal_id=goal_id, user_id=user_id, mode=mode.value)
        return await self._plan_for_month(goal, user_id, target)

    async def get_plan_status(
        self,
        user_id: UserId,
        period_start: date,
        period_end: date,
        today: date | None = None,
    ) -> list[GoalPlanStatus]:
        plans = self._plans
        provider = self._months
        month = first_of_month(period_start)
        if first_of_month(period_end) != month:
            raise InvalidPlanPeriodError("el período debe estar dentro de un solo mes")
        current_month = first_of_month(today or current_today())

        goals = await self._list_all_goals(user_id)
        all_plans = _plans_by_goal(await plans.list_for_user(user_id))
        totals = {
            t.goal_id: t
            for t in await provider.monthly_totals(user_id, month, last_of_month(month))
        }
        # What each goal held when the month began: caps a plan at what was still missing.
        opening = await self._contributions.sums_up_to(user_id, month - timedelta(days=1))

        statuses = (
            _build_status(
                goal,
                month,
                resolve_plan(
                    all_plans.get(goal.id, []), month, _created_month(goal)
                ),
                totals.get(goal.id),
                opening.get(goal.id, Decimal("0")),
                is_current_or_future=month >= current_month,
            )
            for goal in goals
        )
        return [status for status in statuses if status is not None]

    async def get_monthly_history(
        self,
        user_id: UserId,
        months: int = DEFAULT_HISTORY_MONTHS,
        to_month: date | None = None,
        today: date | None = None,
    ) -> list[GoalMonthLine]:
        if not 1 <= months <= MAX_HISTORY_MONTHS:
            raise InvalidPlanPeriodError(f"los meses deben estar entre 1 y {MAX_HISTORY_MONTHS}")
        plans = self._plans
        provider = self._months
        current_month = first_of_month(today or current_today())
        end_month = first_of_month(to_month) if to_month else current_month
        start_month = add_months(end_month, -months)
        window = month_range(start_month, end_month)

        goals = await self._list_all_goals(user_id)
        all_plans = _plans_by_goal(await plans.list_for_user(user_id))
        totals = {
            (t.goal_id, t.month): t
            for t in await provider.monthly_totals(user_id, start_month, last_of_month(end_month))
        }
        opening = await self._contributions.sums_up_to(user_id, start_month - timedelta(days=1))

        return [
            line
            for goal in goals
            for line in _goal_history(
                goal,
                window,
                all_plans.get(goal.id, []),
                totals,
                opening.get(goal.id, Decimal("0")),
                current_month,
            )
        ]

    async def get_progress(
        self, goal_id: GoalId, user_id: UserId, as_of: date | None = None
    ) -> GoalProgress:
        goal = await self.get_goal(goal_id, user_id)
        return _build_progress(goal, as_of or current_today())

    async def list_contributions(
        self, goal_id: GoalId, user_id: UserId
    ) -> list[GoalContribution]:
        await self.get_goal(goal_id, user_id)  # existence/ownership check
        return await self._contributions.list_for_goal(user_id, goal_id)

    async def _delete_rows(self, user_id: UserId, rows: Sequence[GoalPlan]) -> None:
        """Delete plan rows one by one (the adapter only filters by equality)."""
        for row in rows:
            await self._plans.delete(user_id, row.goal_id, row.month, row.kind)

    async def _list_all_goals(self, user_id: UserId) -> list[Goal]:
        total = await self._repository.count(user_id)
        return await self._repository.list_page(user_id, limit=max(total, 1), offset=0)

    async def _plan_for_month(self, goal: Goal, user_id: UserId, month: date) -> Decimal | None:
        """Resolve a goal's plan for ``month`` from its stored rows."""
        rows = await self._plans.list_for_goal(user_id, goal.id)
        return resolve_plan(rows, month, _created_month(goal))

    async def _recompute_cache(self, goal: Goal, user_id: UserId) -> Goal:
        """Persist ``current_amount = sum(all contributions)`` and re-derive status.

        The single writer of ``current_amount`` for every ledger mutation: it reads
        the ledger back (never trusting the previous cache) so the invariant
        ``current_amount == sum(contributions)`` holds after each write and any
        prior drift is healed. Completion is re-derived only for ACTIVE/COMPLETED
        goals; paused/cancelled keep their status.
        """
        new_amount = await self._contributions.sum_for_goal(user_id, goal.id)
        data: dict[str, object] = {"current_amount": decimal_to_db(new_amount)}
        status = _status_after(goal, new_amount)
        if status is not None:
            data["status"] = status
        return await self._repository.update(goal.id, user_id, data)


def _status_after(goal: Goal, new_amount: Decimal) -> str | None:
    """Return the status value to persist for ``new_amount``, or None to keep it.

    Only ACTIVE/COMPLETED goals have completion re-derived (reaching the target
    completes, dropping below reopens); paused/cancelled goals are left untouched.
    """
    if goal.status not in (GoalStatus.ACTIVE, GoalStatus.COMPLETED):
        return None
    reached = new_amount >= goal.target_amount
    return str((GoalStatus.COMPLETED if reached else GoalStatus.ACTIVE).value)


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


def _created_month(goal: Goal) -> date:
    """The month a goal was created in, on the app's default-timezone calendar."""
    return goal_created_month(goal.created_at, settings.DEFAULT_TIMEZONE)


def _ensure_not_before_creation(goal: Goal, month: date) -> None:
    """Reject planning a month earlier than the goal's creation month."""
    if month < _created_month(goal):
        raise InvalidPlanPeriodError(
            f"{month.isoformat()[:7]} es anterior a la fecha en que se creó la meta: "
            "no se puede planear antes de crear la meta"
        )


def _validated_plan_amount(amount: Decimal) -> Decimal:
    """Return ``amount`` rounded to cents, or raise ``InvalidAmountError``.

    A plan may be 0 ("don't plan") but never negative, non-finite or beyond what
    the NUMERIC(12, 2) column can store.
    """
    if not amount.is_finite() or amount < 0:
        raise InvalidAmountError(float(amount), "Plan amount must be zero or positive")
    if amount > MAX_PLANNED_AMOUNT:
        raise InvalidAmountError(float(amount), "Plan amount is too large")
    return amount.quantize(PLAN_AMOUNT_QUANTUM)


def _plans_by_goal(plans: Sequence[GoalPlan]) -> dict[str, list[GoalPlan]]:
    """Group plan rows by goal id."""
    grouped: dict[str, list[GoalPlan]] = defaultdict(list)
    for plan in plans:
        grouped[plan.goal_id].append(plan)
    return grouped


def _build_status(
    goal: Goal,
    month: date,
    planned: Decimal | None,
    totals: GoalMonthContribution | None,
    opening: Decimal,
    *,
    is_current_or_future: bool,
) -> GoalPlanStatus | None:
    """Evaluate a goal's plan for ``month``, or ``None`` when it doesn't belong in it.

    Left out: goals without a plan (or a plan of 0) in the month; PAUSED/CANCELLED
    goals in the current and future months (pause has no history, so past months
    keep their plans); goals already complete at the start of the month that got
    no contribution in it.
    """
    saved = totals.saved if totals else Decimal("0")
    withdrawn = totals.withdrawn if totals else Decimal("0")

    if planned is None or planned <= 0:
        return None
    if is_current_or_future and goal.status in (GoalStatus.PAUSED, GoalStatus.CANCELLED):
        return None
    # Already complete when the month began and nothing went in: nothing to plan. Judged
    # from the balance at that month, not from the goal's status today.
    if opening >= goal.target_amount and saved <= 0:
        return None

    # A plan bigger than what the goal still lacked is accepted, but "faltan" never
    # asks for more than the goal can take.
    effective = min(planned, max(goal.target_amount - opening, Decimal("0")))
    remaining = max(effective - saved, Decimal("0"))
    percentage = 100.0 if effective == 0 else round(float(saved / effective * 100), 2)
    return GoalPlanStatus(
        goal_id=goal.id,
        goal_name=goal.name,
        currency=goal.currency,
        month=month,
        planned=planned,
        effective_planned=effective,
        contributed_gross=saved,
        withdrawn=withdrawn,
        remaining=remaining,
        percentage=percentage,
        is_met=remaining == 0,
        goal_completed=opening + saved - withdrawn >= goal.target_amount,
    )


def _goal_history(
    goal: Goal,
    window: Sequence[date],
    plans: Sequence[GoalPlan],
    totals: dict[tuple[str, date], GoalMonthContribution],
    opening: Decimal,
    current_month: date,
) -> list[GoalMonthLine]:
    """Build a goal's month lines over ``window`` (oldest first).

    A month is listed when the goal had movement in it, a plan for it, or it is a
    past/current month from the goal's creation on; future months need a plan.
    """
    created = _created_month(goal)
    movements = [totals.get((goal.id, month)) for month in window]
    nets = ((m.saved - m.withdrawn) if m else Decimal("0") for m in movements)
    balances = list(accumulate(nets, initial=opening))  # balances[i] = start of window[i]

    return [
        GoalMonthLine(
            goal_id=goal.id,
            goal_name=goal.name,
            currency=goal.currency,
            month=month,
            planned=planned,
            # The plan capped at what the goal still lacked when the month began.
            effective_planned=(
                min(planned, max(goal.target_amount - start, Decimal("0")))
                if planned is not None
                else None
            ),
            saved=movement.saved if movement else Decimal("0"),
            withdrawn=movement.withdrawn if movement else Decimal("0"),
            cumulative=end,
        )
        for month, movement, start, end in zip(
            window, movements, balances[:-1], balances[1:], strict=True
        )
        for planned in [resolve_plan(plans, month, created)]
        if movement is not None or planned is not None or created <= month <= current_month
    ]

