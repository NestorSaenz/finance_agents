"""Contracts (ABCs) for the goals module."""

from abc import ABC, abstractmethod
from datetime import date
from decimal import Decimal
from typing import Any

from app.shared.types import GoalId, GoalPlanClearMode, GoalPlanKind, GoalPlanScope, UserId

from .models import (
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


class GoalRepositoryABC(ABC):
    """Contract for goal persistence (data access only)."""

    @abstractmethod
    async def create(self, goal: GoalCreate, user_id: UserId) -> Goal:
        """Persist a new goal and return it."""

    @abstractmethod
    async def get_by_id(self, goal_id: GoalId, user_id: UserId) -> Goal | None:
        """Return a goal owned by ``user_id`` or ``None`` if missing."""

    @abstractmethod
    async def list_page(self, user_id: UserId, *, limit: int, offset: int) -> list[Goal]:
        """Return a page of goals for a user, by priority then newest."""

    @abstractmethod
    async def count(self, user_id: UserId) -> int:
        """Return the total number of goals for a user."""

    @abstractmethod
    async def update(
        self, goal_id: GoalId, user_id: UserId, data: dict[str, Any]
    ) -> Goal:
        """Apply partial updates to a goal and return the updated goal."""

    @abstractmethod
    async def delete(self, goal_id: GoalId, user_id: UserId) -> None:
        """Delete a user's goal (scoped by ``user_id``)."""


class GoalContributionRepositoryABC(ABC):
    """Contract for dated goal-contribution persistence (data access only)."""

    @abstractmethod
    async def create(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date,
    ) -> GoalContribution:
        """Persist a dated contribution toward a goal and return it."""

    @abstractmethod
    async def sums_up_to(self, user_id: UserId, as_of: date) -> dict[str, Decimal]:
        """Return ``goal_id -> sum`` of contributions dated on or before ``as_of``.

        One fetch of the user's contributions, grouped in Python: PostgREST has
        no range filter, so the date window is applied in Python (as in
        ``CardPaymentRepository.total_paid``).
        """

    @abstractmethod
    async def sum_for_goal(self, user_id: UserId, goal_id: GoalId) -> Decimal:
        """Return the signed sum of ALL of a goal's contributions (no date bound).

        This is the ledger balance a goal's cached ``current_amount`` must equal.
        One fetch, summed in Python (mirrors ``sum_in_period``).
        """

    @abstractmethod
    async def sum_in_period(
        self, user_id: UserId, start: date, end: date
    ) -> Decimal:
        """Return the total of the user's contributions within ``[start, end]``.

        Bounds are inclusive. One fetch of the user's contributions, filtered in
        Python (like ``sums_up_to``) since PostgREST has no range filter.
        """

    @abstractmethod
    async def list_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[GoalContribution]:
        """Return the user's contributions within the date range, newest first."""

    @abstractmethod
    async def list_for_goal(
        self, user_id: UserId, goal_id: GoalId
    ) -> list[GoalContribution]:
        """Return a goal's contributions, newest ``contribution_date`` first."""

    @abstractmethod
    async def delete(self, contribution_id: str, user_id: UserId) -> None:
        """Delete a single contribution (scoped by ``user_id``)."""


class GoalPlanRepositoryABC(ABC):
    """Contract for goal-plan persistence (data access only)."""

    @abstractmethod
    async def list_for_user(self, user_id: UserId) -> list[GoalPlan]:
        """Return every plan row of the user (all goals), oldest month first."""

    @abstractmethod
    async def list_for_goal(self, user_id: UserId, goal_id: GoalId) -> list[GoalPlan]:
        """Return a goal's plan rows, oldest month first."""

    @abstractmethod
    async def upsert(
        self,
        user_id: UserId,
        goal_id: GoalId,
        month: date,
        kind: GoalPlanKind,
        amount: Decimal,
    ) -> GoalPlan:
        """Create or update the ``(goal, month, kind)`` row and return it.

        ``month`` must already be the first day of the month.
        """

    @abstractmethod
    async def delete(
        self, user_id: UserId, goal_id: GoalId, month: date, kind: GoalPlanKind
    ) -> None:
        """Delete the ``(goal, month, kind)`` row (a no-op when it does not exist)."""


class ContributionMonthsProviderABC(ABC):
    """Contract for the gross contributed amounts per goal and month."""

    @abstractmethod
    async def monthly_totals(
        self, user_id: UserId, start: date, end: date
    ) -> list[GoalMonthContribution]:
        """Return gross ``saved``/``withdrawn`` per ``(goal, month)`` within ``[start, end]``.

        Months with no movement produce no entry. Grouped by the month of each
        contribution's date; sorted by goal then month.
        """


class GoalServiceABC(ABC):
    """Contract for goal use cases (business logic)."""

    @abstractmethod
    async def create_goal(self, goal: GoalCreate, user_id: UserId) -> Goal:
        """Create a financial goal."""

    @abstractmethod
    async def get_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        """Return a goal or raise ``GoalNotFoundError``."""

    @abstractmethod
    async def list_goals(
        self,
        user_id: UserId,
        *,
        page: int,
        page_size: int,
        as_of: date | None = None,
    ) -> tuple[list[Goal], int]:
        """Return a page of goals and the total count.

        With ``as_of`` set, each goal's ``current_amount`` (and status) reflects
        its cumulative contributions up to that month-end, not the running total.
        """

    @abstractmethod
    async def contribute(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date | None = None,
    ) -> Goal:
        """Record a dated contribution, completing the goal if the target is reached.

        ``contribution_date`` defaults to the caller's local today (``current_today()``:
        the turn's bound day, else the ``DEFAULT_TIMEZONE`` day); the REST route passes
        the user's local date explicitly.
        """

    @abstractmethod
    async def withdraw_from_goal(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        withdrawal_date: date,
    ) -> Goal:
        """Withdraw ``amount`` from a goal, returning the money to disponible.

        A withdrawal is recorded as a NEGATIVE dated contribution: it reduces the
        goal's ``current_amount`` and, since aportes are netted out of disponible,
        the money returns there. It is neither an income nor an expense.

        Raises ``GoalNotFoundError`` if the goal is missing and
        ``GoalWithdrawalExceedsBalanceError`` when ``amount`` exceeds the balance.
        """

    @abstractmethod
    async def set_goal_amount(
        self, goal_id: GoalId, user_id: UserId, amount: Decimal, on_date: date
    ) -> Goal:
        """Reconcile a goal's saved amount to ``amount``, keeping the ledger honest.

        Let ``s`` be the goal's ledger balance (sum of its contributions):

        - ``amount == s``: pure reconcile — set ``current_amount`` to ``amount``
          and write NO ledger row (zero cash-flow impact).
        - ``amount > s``: real money in — record a ``amount - s`` contribution.
        - ``amount < s``: real money out — withdraw ``s - amount``.

        Raises ``InvalidAmountError`` when ``amount`` is negative and
        ``GoalNotFoundError`` when the goal is missing.
        """

    @abstractmethod
    async def contributed_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> Decimal:
        """Return the total contributed to all goals within ``[period_start, period_end]``."""

    @abstractmethod
    async def list_contributions_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[GoalContributionView]:
        """Return the user's goal contributions in the period, with goal names.

        Contributions are newest first; a contribution whose goal was deleted
        falls back to the name "Meta". Mirrors ``list_payments`` for cards.
        """

    @abstractmethod
    async def get_progress(
        self, goal_id: GoalId, user_id: UserId, as_of: date | None = None
    ) -> GoalProgress:
        """Return a goal evaluated against its target and timeline."""

    @abstractmethod
    async def list_contributions(
        self, goal_id: GoalId, user_id: UserId
    ) -> list[GoalContribution]:
        """Return a goal's dated contributions (newest first).

        Verifies existence/ownership first, raising ``GoalNotFoundError``.
        """

    @abstractmethod
    async def update_goal(
        self,
        goal_id: GoalId,
        user_id: UserId,
        *,
        name: str | None = None,
        target_amount: Decimal | None = None,
        target_date: date | None = None,
    ) -> Goal:
        """Change a goal's name/target/date; return it (or raise ``GoalNotFoundError``)."""

    @abstractmethod
    async def delete_goal(self, goal_id: GoalId, user_id: UserId) -> Goal:
        """Delete a goal and return it (or raise ``GoalNotFoundError``)."""

    @abstractmethod
    async def remove_contribution(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date | None = None,
    ) -> Goal | None:
        """Delete a single dated contribution and return the updated goal.

        Matches by ``amount`` and, when given, ``contribution_date``; on several
        matches the most recent is removed. Returns ``None`` when no contribution
        matches (the goal itself must exist, else ``GoalNotFoundError``).
        """

    @abstractmethod
    async def set_paused(
        self, goal_id: GoalId, user_id: UserId, paused: bool
    ) -> Goal:
        """Pause or resume a goal, returning it (or raise ``GoalNotFoundError``).

        Pausing sets the status to PAUSED (contributions keep working but the goal
        reads as parked). Resuming re-derives ACTIVE/COMPLETED from the saved
        amount vs the target. Idempotent: pausing a paused goal (or resuming an
        active one) is a harmless no-op.
        """

    @abstractmethod
    async def set_plan(
        self,
        user_id: UserId,
        goal_id: GoalId,
        amount: Decimal,
        month: date,
        scope: GoalPlanScope,
    ) -> Decimal | None:
        """Plan ``amount`` for a goal in ``month`` and return that month's plan afterwards.

        ``month`` is normalized to its first day. ``SOLO_MES`` writes an override
        for that month only; ``DESDE_MES`` writes a recurring from that month on
        (dropping that month's override so it takes effect). Past and future months
        are allowed. Raises ``InvalidAmountError`` for a negative amount and
        ``GoalNotFoundError`` when the goal is missing.
        """

    @abstractmethod
    async def clear_plan(
        self,
        user_id: UserId,
        goal_id: GoalId,
        month: date,
        mode: GoalPlanClearMode,
    ) -> Decimal | None:
        """Clear a goal's plan for ``month`` and return that month's plan afterwards.

        ``SIN_PLAN``: this month I don't plan (override of 0). ``VOLVER_AL_GENERAL``:
        drop the month's override so the recurring applies again. ``TERMINAR``: stop
        planning from this month on (recurring of 0). Raises ``GoalNotFoundError``.
        """

    @abstractmethod
    async def get_plan_status(
        self,
        user_id: UserId,
        period_start: date,
        period_end: date,
        today: date | None = None,
    ) -> list[GoalPlanStatus]:
        """Return plan vs contributed for the single month of ``[period_start, period_end]``.

        Includes ACTIVE goals planning more than 0 that month, and COMPLETED goals
        that received contributions in it. PAUSED/CANCELLED goals are left out of the
        current and future months (``today`` defaults to ``current_today()``), while
        past months keep their plans. Raises ``InvalidPlanPeriodError`` when the
        range spans more than one month.
        """

    @abstractmethod
    async def get_monthly_history(
        self,
        user_id: UserId,
        months: int = 6,
        to_month: date | None = None,
        today: date | None = None,
    ) -> list[GoalMonthLine]:
        """Return plan vs contributed per goal and month, ``months`` months before
        ``to_month`` plus ``to_month`` itself (default: the current month).

        Future months only appear for goals that have a plan in them. Lines are
        ordered by goal, then month.
        """
