"""Holistic financial analysis: read-only cross-module aggregation."""

import asyncio
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

    async def snapshot(self, user_id: UserId, period: str) -> FinancialSnapshot:
        start, end = resolve_period(period)

        # These reads are independent, so fetch them concurrently instead of
        # paying five sequential round-trips.
        summary, profile, budget_statuses, goals_page, card_statuses = (
            await asyncio.gather(
                self._transactions.get_spending_summary(
                    user_id, period_start=start, period_end=end
                ),
                self._profiles.get_profile(user_id),
                self._budgets.get_all_status(user_id),
                self._goals.list_goals(user_id, page=1, page_size=_GOALS_PAGE),
                self._cards.get_all_status(user_id),
            )
        )
        goals = goals_page[0]

        # The reference income is a monthly figure, so it only applies this month.
        income_base = (
            profile.monthly_income or Decimal("0")
            if period == ESTE_MES
            else Decimal("0")
        )
        income_registered = summary.total_income
        total_income = income_base + income_registered
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
