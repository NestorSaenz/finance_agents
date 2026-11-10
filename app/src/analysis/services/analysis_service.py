"""Holistic financial analysis: read-only cross-module aggregation."""

import asyncio
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Final

import httpx
from postgrest.exceptions import APIError

from app.core.config import settings
from app.core.exceptions import FinanceGPTError
from app.core.logging import get_logger
from app.shared.periods import ESTE_MES, recent_months, resolve_period
from app.shared.types import UserId
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.goals.interfaces import GoalServiceABC
from app.src.goals.models import GoalFlows, GoalMonthLine
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.users.interfaces import UserProfileServiceABC

from ..constants import MAX_TREND_MONTHS, MIN_TREND_MONTHS
from ..interfaces import AnalysisServiceABC
from ..models import (
    BudgetLine,
    CardLine,
    CategoryLine,
    FinancialSnapshot,
    GoalLine,
    MonthlyTotals,
    PeriodSpending,
)

logger = get_logger(__name__)

# Failures reading the (informational) goal-plan data: domain/infrastructure errors and
# the database client's own (missing table, network).
_PLAN_DATA_FAILURES: Final = (FinanceGPTError, APIError, httpx.HTTPError)

# Goals/cards are cumulative; a generous page keeps personal-finance volumes in one read.
_GOALS_PAGE: int = 50

# "Accumulated surplus" sums over all history, so its window opens at the epoch.
_EPOCH: date = date(1970, 1, 1)


async def _no_flows() -> GoalFlows:
    """No goal flows count (the whole period is before the cutoff)."""
    return GoalFlows(saved=Decimal("0"), withdrawn=Decimal("0"))


class AnalysisService(AnalysisServiceABC):
    """Builds a grounded financial snapshot from the domain services."""

    def __init__(
        self,
        transactions: TransactionServiceABC,
        budgets: BudgetServiceABC,
        goals: GoalServiceABC,
        cards: CreditCardServiceABC,
        profiles: UserProfileServiceABC,
    ) -> None:
        self._transactions = transactions
        self._budgets = budgets
        self._goals = goals
        self._cards = cards
        self._profiles = profiles

    async def snapshot(
        self, user_id: UserId, period: str, today: date | None = None
    ) -> FinancialSnapshot:
        # ``today`` (the user's local day) anchors the period window; None → UTC.
        start, end = resolve_period(period, today=today)

        # These reads are independent, so fetch them concurrently instead of
        # paying five sequential round-trips.
        spending, profile, budget_statuses, goals_page, card_statuses, goal_months = (
            await asyncio.gather(
                self.period_spending(user_id, start, end),
                self._profiles.get_profile(user_id),
                # Anchor budget periods and card cycles on the user's local day
                # (None → the services' own UTC fallback) so a near-midnight
                # analysis doesn't mix a local transaction window with UTC statuses.
                self._budgets.get_all_status(user_id, as_of=today),
                self._goals.list_goals(
                    user_id, page=1, page_size=_GOALS_PAGE, as_of=end
                ),
                self._cards.get_all_status(user_id, as_of=today),
                self._goal_month_lines(user_id, start, end, today),
            )
        )
        summary = spending.summary
        goals = goals_page[0]
        by_goal = {line.goal_id: line for line in goal_months}

        # The profile's monthly income is a FALLBACK, not additive: it only counts
        # when this month has no logged income, so a registered income replaces it
        # instead of stacking on top. It's a monthly figure, so only for este_mes.
        income_registered = summary.total_income
        income_base = (
            profile.monthly_income or Decimal("0")
            if period == ESTE_MES
            else Decimal("0")
        )
        total_income = income_registered if income_registered > 0 else income_base
        disposable = total_income - spending.total_spent

        pct = profile.savings_goal_percentage
        savings_target = total_income * pct / 100 if pct is not None else None

        cards = [
            CardLine(
                name=s.card.name,
                balance=s.balance,
                limit=s.card.credit_limit,
                available=s.available,
                next_payment_date=s.next_payment_date,
                statement_amount=s.statement_amount,
                overdue_amount=s.overdue_amount,
            )
            for s in card_statuses
        ]
        return FinancialSnapshot(
            period=period,
            income_base=income_base,
            income_registered=income_registered,
            total_income=total_income,
            total_expenses=summary.total_expenses,
            goal_saved=spending.goal_saved,
            goal_withdrawn=spending.goal_withdrawn,
            credit_expenses=summary.credit_expenses,
            cash_expenses=summary.cash_expenses,
            disposable=disposable,
            savings_target_pct=pct,
            savings_target_amount=savings_target,
            by_category=[
                CategoryLine(
                    category=c.category,
                    amount=c.amount,
                    percentage=(
                        float(c.amount / summary.total_expenses * 100)
                        if summary.total_expenses > 0
                        else 0.0
                    ),
                )
                for c in summary.by_category
            ],
            budgets=[
                BudgetLine(
                    category=s.budget.category,
                    name=s.budget.name,
                    spent=s.spent,
                    fixed=s.spent_fixed,
                    limit=s.budget.amount,
                    percentage=s.percentage,
                )
                for s in budget_statuses
            ],
            goals=[
                GoalLine(
                    name=g.name,
                    current=g.current_amount,
                    target=g.target_amount,
                    percentage=(
                        float(g.current_amount / g.target_amount * 100)
                        if g.target_amount > 0
                        else 0.0
                    ),
                    planned_monthly=(
                        by_goal[g.id].planned if g.id in by_goal else None
                    ),
                    currency=g.currency,
                    contributed_this_period=(
                        by_goal[g.id].saved if g.id in by_goal else Decimal("0")
                    ),
                )
                for g in goals
            ],
            cards=cards,
            card_debt_total=sum((c.balance for c in cards), Decimal("0")),
            card_available_total=sum((c.available for c in cards), Decimal("0")),
        )

    async def period_spending(
        self, user_id: UserId, start: date, end: date
    ) -> PeriodSpending:
        cutoff = settings.GOALS_COUNT_AS_SPENDING_FROM
        # Only the part of the period on/after the cutoff is reported, for the money set
        # aside AND the money that came back (no asymmetry between the two). The surplus
        # and the final cash use their own unclipped flows and are not affected.
        if end < cutoff:
            counted = _no_flows()
        elif start >= cutoff:
            counted = None  # the whole period counts: one read serves both figures
        else:
            counted = self._goals.flows_in_period(user_id, cutoff, end)
        summary, full = await asyncio.gather(
            self._transactions.get_spending_summary(user_id, period_start=start, period_end=end),
            self._goals.flows_in_period(user_id, start, end),
        )
        clipped = full if counted is None else await counted
        return PeriodSpending(
            summary=summary, goal_saved=clipped.saved, goal_withdrawn=clipped.withdrawn
        )

    async def _goal_month_lines(
        self, user_id: UserId, start: date, end: date, today: date | None
    ) -> list[GoalMonthLine]:
        """Each goal's plan and gross contributions for the period's month.

        Only a single-month period has a monthly plan; for a wider one (e.g. "todo")
        there is nothing to report, so the goal lines keep their defaults.
        """
        if (start.year, start.month) != (end.year, end.month):
            return []
        try:
            history = await self._goals.get_monthly_history(
                user_id, months=1, to_month=start, today=today
            )
        except _PLAN_DATA_FAILURES as e:
            # Informational data: the analysis must not fail because the plan can't be read.
            logger.warning("Goal plan data unavailable for the analysis", error=str(e))
            return []
        return [line for line in history if line.month == start.replace(day=1)]

    async def monthly_trend(
        self, user_id: UserId, months: int, today: date | None = None
    ) -> list[MonthlyTotals]:
        # One aggregation per month, reusing the SAME summary the single-period
        # snapshot uses: the trend's "this month" is then identical to
        # analyze_finances' "this month" by construction, instead of a second
        # aggregation that could drift from it.
        #
        # Buckets by transaction_date (get_spending_summary's field): the question
        # behind a trend is "when did I spend", so a credit purchase counts in the
        # month it was made. Attributing by budget_date would move charges to their
        # statement month and contradict every other spending figure the assistant
        # reports for that month.
        count = max(MIN_TREND_MONTHS, min(months, MAX_TREND_MONTHS))
        keys = recent_months(count, today=today)
        # The months are independent reads; gather them instead of paying one
        # round-trip per month sequentially.
        windows = [resolve_period(key) for key in keys]
        summaries, monthly = await asyncio.gather(
            asyncio.gather(
                *(
                    self._transactions.get_spending_summary(
                        user_id, period_start=start, period_end=end
                    )
                    for start, end in windows
                )
            ),
            # ONE read of the goal flows for the whole window (RPC, Python fallback).
            self._goals.monthly_flows(user_id, windows[0][0], windows[-1][1]),
        )
        # The provider returns one row per goal and month: add the goals up per month.
        saved_by_month: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in monthly:
            saved_by_month[row.month] += row.saved
        cutoff = settings.GOALS_COUNT_AS_SPENDING_FROM
        saved = [
            await self._month_goal_saved(user_id, start, end, cutoff, saved_by_month)
            for start, end in windows
        ]
        return [
            MonthlyTotals(
                month=key,
                income=summary.total_income,
                expenses=summary.total_expenses + goal_saved,
                balance=summary.total_income - summary.total_expenses - goal_saved,
                goal_saved=goal_saved,
            )
            for key, summary, goal_saved in zip(keys, summaries, saved, strict=True)
        ]

    async def _month_goal_saved(
        self,
        user_id: UserId,
        start: date,
        end: date,
        cutoff: date,
        saved_by_month: dict[date, Decimal],
    ) -> Decimal:
        """What was set aside into goals in one month, counting only from the cutoff on."""
        if end < cutoff:
            return Decimal("0")
        if start >= cutoff:
            return saved_by_month.get(start, Decimal("0"))
        # The cutoff falls inside this month: only its tail counts.
        return (await self._goals.flows_in_period(user_id, cutoff, end)).saved

    async def accumulated_surplus(self, user_id: UserId, as_of: date) -> Decimal:
        # Free cash that carries over month to month: everything that ever came in
        # minus everything that left the pocket (cash spent, card payments) and what
        # was earmarked into goals — all cumulative up to `as_of`. The three reads
        # are independent, so gather them concurrently like `snapshot`.
        summary, card_paid, goal_saved = await asyncio.gather(
            self._transactions.get_spending_summary(
                user_id, period_start=_EPOCH, period_end=as_of
            ),
            self._cards.total_paid_up_to(user_id, as_of),
            self._goals.contributed_in_period(user_id, _EPOCH, as_of),
        )
        return summary.total_income - summary.cash_expenses - card_paid - goal_saved
