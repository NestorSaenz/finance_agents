"""Data Transfer Objects for the analysis API layer."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.src.transactions.dto import CategorySpendingResponse, SpendingSummaryResponse

from .models import PeriodSpending


class AccumulatedSurplusResponse(BaseModel):
    """Free (unearmarked) cash accumulated up to the selected month-end."""

    accumulated_surplus: Decimal = Field(
        ...,
        description="Cumulative disponible real up to the period's month-end "
        "(income − cash − card payments − goal contributions). Carries over month "
        "to month; can be negative. Decimal serialized as string.",
    )


class PeriodSpendingResponse(BaseModel):
    """A period's spending: consumption (as in /transactions/summary) plus goal savings.

    ``total_expenses``, ``by_category`` (shares over the consumption), ``credit_expenses``
    and ``cash_expenses`` mean exactly what they do in /transactions/summary (CONSUMPTION
    only; credit + cash == total_expenses). ``balance`` here is DIFFERENT (registered income only, no base fallback): it already
    includes the money set aside into goals.
    """

    period: str
    total_income: Decimal
    total_expenses: Decimal = Field(..., description="Consumption only (no goal savings)")
    by_category: list[CategorySpendingResponse]
    credit_expenses: Decimal
    cash_expenses: Decimal
    goal_saved: Decimal = Field(
        ..., description="Gross set aside into goals that counts as spending (>= the cutoff)"
    )
    goal_withdrawn: Decimal = Field(
        ..., description="Gross that came back from goals in the whole period (informational)"
    )
    total_spent: Decimal = Field(..., description="total_expenses + goal_saved")
    balance: Decimal = Field(
        ...,
        description=(
            "REGISTERED income - total_spent (goal savings included), WITHOUT the base-income "
            "fallback: a client that applies that fallback recomputes the balance itself."
        ),
    )
    goal_spending_from: date = Field(
        ..., description="Contributions dated on/after this day count as spending"
    )

    @classmethod
    def from_domain(
        cls, spending: PeriodSpending, period: str, spending_from: date
    ) -> "PeriodSpendingResponse":
        summary = spending.summary
        return cls(
            period=period,
            total_income=summary.total_income,
            total_expenses=summary.total_expenses,
            # Same shares over the consumption as /transactions/summary (one implementation).
            by_category=SpendingSummaryResponse.from_domain(summary, period).by_category,
            credit_expenses=summary.credit_expenses,
            cash_expenses=summary.cash_expenses,
            goal_saved=spending.goal_saved,
            goal_withdrawn=spending.goal_withdrawn,
            total_spent=spending.total_spent,
            balance=spending.balance,
            goal_spending_from=spending_from,
        )
