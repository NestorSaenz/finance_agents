"""Gross monthly contributions per goal: Postgres function with a Python fallback."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Final

import httpx
from postgrest.exceptions import APIError

from app.core.exceptions import DatabaseError
from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface
from app.shared.parsing import parse_decimal as _parse_decimal
from app.shared.types import UserId

from ..constants import GOAL_MONTHLY_CONTRIBUTIONS_RPC
from ..interfaces import ContributionMonthsProviderABC, GoalContributionRepositoryABC
from ..models import GoalContribution, GoalMonthContribution
from ..planning import first_of_month

logger = get_logger(__name__)

# Failures of the RPC call itself (function missing -> APIError, network, DB layer).
_RPC_FAILURES: Final = (DatabaseError, APIError, httpx.HTTPError)

_ZERO: Final[Decimal] = Decimal("0")


class ContributionMonthsProvider(ContributionMonthsProviderABC):
    """Gross ``saved``/``withdrawn`` per goal and month.

    Prefers the server-side ``goal_monthly_contributions`` function (migration 018):
    one aggregate query. Falls back to grouping the contributions in Python when the
    function isn't present yet or answers garbage, so it works either way (mirrors
    ``TransactionSpendingProvider`` for budgets).
    """

    def __init__(
        self, db: DatabaseInterface, contributions: GoalContributionRepositoryABC
    ) -> None:
        self._db = db
        self._contributions = contributions

    async def monthly_totals(
        self, user_id: UserId, start: date, end: date
    ) -> list[GoalMonthContribution]:
        try:
            result = await self._db.execute_rpc(
                GOAL_MONTHLY_CONTRIBUTIONS_RPC,
                {
                    "p_user_id": user_id,
                    "p_start": start.isoformat(),
                    "p_end": end.isoformat(),
                },
            )
            # An empty result is a valid answer (no movement), not a reason to fall back.
            return sorted(
                (_parse_rpc_row(row) for row in result.data), key=_sort_key
            )
        except _RPC_FAILURES as e:
            logger.warning(
                "goal_monthly_contributions RPC failed; falling back to Python", error=str(e)
            )
        except ValueError as e:
            logger.warning(
                "goal_monthly_contributions RPC returned a malformed row; "
                "falling back to Python",
                error=str(e),
            )

        contributions = await self._contributions.list_in_period(user_id, start, end)
        return _group_in_python(contributions)


def _sort_key(item: GoalMonthContribution) -> tuple[str, date]:
    return item.goal_id, item.month


def _parse_rpc_row(row: object) -> GoalMonthContribution:
    """Map one RPC row to the domain model; ``ValueError`` when it is malformed."""
    if not isinstance(row, dict):
        raise ValueError(f"RPC row is not an object: {row!r}")
    missing = [k for k in ("goal_id", "month", "saved", "withdrawn") if row.get(k) is None]
    if missing:
        raise ValueError(f"RPC row is missing {missing}")
    # Strict on purpose: a lenient parse would silently turn garbage into "today".
    month = date.fromisoformat(str(row["month"])[:10])  # ValueError -> Python fallback
    return GoalMonthContribution(
        goal_id=str(row["goal_id"]),
        month=first_of_month(month),
        saved=_parse_decimal(row["saved"]),
        withdrawn=_parse_decimal(row["withdrawn"]),
    )


def _group_in_python(contributions: list[GoalContribution]) -> list[GoalMonthContribution]:
    """Group dated contributions into gross saved/withdrawn per (goal, month)."""
    saved: dict[tuple[str, date], Decimal] = defaultdict(lambda: _ZERO)
    withdrawn: dict[tuple[str, date], Decimal] = defaultdict(lambda: _ZERO)
    for c in contributions:
        key = (c.goal_id, first_of_month(c.contribution_date))
        if c.amount > 0:
            saved[key] += c.amount
        elif c.amount < 0:
            withdrawn[key] += -c.amount
    return [
        GoalMonthContribution(
            goal_id=goal_id,
            month=month,
            saved=saved.get((goal_id, month), _ZERO),
            withdrawn=withdrawn.get((goal_id, month), _ZERO),
        )
        for goal_id, month in sorted(saved.keys() | withdrawn.keys())
    ]
