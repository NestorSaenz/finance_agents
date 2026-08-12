"""Holistic financial analysis: read-only cross-module aggregation."""

import asyncio
from datetime import date
from decimal import Decimal

from app.shared.periods import ESTE_MES, resolve_period
from app.shared.types import UserId
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.cards.interfaces import CreditCardServiceABC
from app.src.goals.interfaces import GoalServiceABC
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.users.interfaces import UserProfileServiceABC

from ..interfaces import AnalysisServiceABC
from ..models import (
    BudgetLine,
    CardLine,
    CategoryLine,
    FinancialSnapshot,
    GoalLine,
)

# Goals/cards are cumulative; a generous page keeps personal-finance volumes in one read.
_GOALS_PAGE: int = 50

# "Accumulated surplus" sums over all history, so its window opens at the epoch.
_EPOCH: date = date(1970, 1, 1)


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
        summary, profile, budget_statuses, goals_page, card_statuses = (
            await asyncio.gather(
                self._transactions.get_spending_summary(
                    user_id, period_start=start, period_end=end
                ),
                self._profiles.get_profile(user_id),
                # Anchor budget periods and card cycles on the user's local day
                # (None → the services' own UTC fallback) so a near-midnight
                # analysis doesn't mix a local transaction window with UTC statuses.
                self._budgets.get_all_status(user_id, as_of=today),
                self._goals.list_goals(
                    user_id, page=1, page_size=_GOALS_PAGE, as_of=end
                ),
                self._cards.get_all_status(user_id, as_of=today),
            )
        )
        goals = goals_page[0]

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
        disposable = total_income - summary.total_expenses

        pct = profile.savings_goal_percentage
        savings_target = total_income * pct / 100 if pct is not None else None

        cards = [
            CardLine(
                name=s.card.name,
                balance=s.balance,
                limit=s.card.credit_limit,
                available=s.available,
                next_payment_date=s.next_payment_date,
            )
            for s in card_statuses
        ]
        return FinancialSnapshot(
            period=period,
            income_base=income_base,
            income_registered=income_registered,
            total_income=total_income,
            total_expenses=summary.total_expenses,
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
                )
                for g in goals
            ],
            cards=cards,
            card_debt_total=sum((c.balance for c in cards), Decimal("0")),
            card_available_total=sum((c.available for c in cards), Decimal("0")),
        )

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
