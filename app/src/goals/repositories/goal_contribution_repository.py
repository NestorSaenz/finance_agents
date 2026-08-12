"""Supabase-backed goal-contribution repository (data access only)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Final

from app.core.exceptions import InfrastructureError
from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import parse_date as _parse_date
from app.shared.parsing import parse_datetime as _parse_datetime
from app.shared.parsing import parse_decimal as _parse_decimal
from app.shared.serialization import decimal_to_db
from app.shared.types import GoalId, UserId

from ..interfaces import GoalContributionRepositoryABC
from ..models import GoalContribution

logger = get_logger(__name__)

GOAL_CONTRIBUTIONS_TABLE: Final[str] = "goal_contributions"


class GoalContributionRepository(GoalContributionRepositoryABC):
    """Persists dated goal contributions in Supabase."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def create(
        self,
        goal_id: GoalId,
        user_id: UserId,
        amount: Decimal,
        contribution_date: date,
    ) -> GoalContribution:
        row = {
            "user_id": user_id,
            "goal_id": goal_id,
            "amount": decimal_to_db(amount),
            "contribution_date": contribution_date.isoformat(),
        }
        result = await self._db.insert(GOAL_CONTRIBUTIONS_TABLE, row)
        if not result.data:
            raise InfrastructureError(
                "Goal contribution insert returned no rows",
                code="GOAL_CONTRIBUTION_INSERT_FAILED",
            )
        created = _row_to_contribution(result.data[0])
        logger.info("Goal contribution created", goal_id=goal_id, user_id=user_id)
        return created

    async def sums_up_to(self, user_id: UserId, as_of: date) -> dict[str, Decimal]:
        config = QueryConfig(
            select="goal_id,amount,contribution_date",
            filters={"user_id": user_id},
        )
        result = await self._db.select(GOAL_CONTRIBUTIONS_TABLE, config)
        # `as_of` reconstructs each goal's progress at a past month-end: only
        # contributions on or before that date count. PostgREST equality filters
        # can't do ranges, so the date window is applied in Python.
        totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in result.data:
            contribution_date = _parse_date(row.get("contribution_date"))
            if contribution_date <= as_of:
                totals[str(row["goal_id"])] += _parse_decimal(row.get("amount"))
        return dict(totals)

    async def sum_for_goal(self, user_id: UserId, goal_id: GoalId) -> Decimal:
        config = QueryConfig(
            select="amount",
            filters={"user_id": user_id, "goal_id": goal_id},
        )
        result = await self._db.select(GOAL_CONTRIBUTIONS_TABLE, config)
        # Signed sum of every contribution for the goal (positive aportes and
        # negative withdrawals) — the ledger balance the goal's cached
        # ``current_amount`` must equal. Summed in Python, like ``sum_in_period``.
        return sum(
            (_parse_decimal(row.get("amount")) for row in result.data),
            start=Decimal("0"),
        )

    async def sum_in_period(
        self, user_id: UserId, start: date, end: date
    ) -> Decimal:
        config = QueryConfig(
            select="amount,contribution_date",
            filters={"user_id": user_id},
        )
        result = await self._db.select(GOAL_CONTRIBUTIONS_TABLE, config)
        # Inclusive [start, end] window applied in Python (PostgREST equality
        # filters can't express ranges), mirroring ``sums_up_to``.
        return sum(
            (
                _parse_decimal(row.get("amount"))
                for row in result.data
                if start <= _parse_date(row.get("contribution_date")) <= end
            ),
            start=Decimal("0"),
        )

    async def list_in_period(
        self, user_id: UserId, period_start: date, period_end: date
    ) -> list[GoalContribution]:
        config = QueryConfig(
            filters={"user_id": user_id},
            order_by="contribution_date",
            order_ascending=False,
        )
        result = await self._db.select(GOAL_CONTRIBUTIONS_TABLE, config)
        contributions = [_row_to_contribution(row) for row in result.data]
        # Inclusive [start, end] window applied in Python (PostgREST equality
        # filters can't express ranges), mirroring ``CardPaymentRepository``.
        return [
            c for c in contributions if period_start <= c.contribution_date <= period_end
        ]

    async def list_for_goal(
        self, user_id: UserId, goal_id: GoalId
    ) -> list[GoalContribution]:
        config = QueryConfig(
            filters={"user_id": user_id, "goal_id": goal_id},
            order_by="contribution_date",
            order_ascending=False,
        )
        result = await self._db.select(GOAL_CONTRIBUTIONS_TABLE, config)
        return [_row_to_contribution(row) for row in result.data]

    async def delete(self, contribution_id: str, user_id: UserId) -> None:
        await self._db.delete(
            GOAL_CONTRIBUTIONS_TABLE, {"id": contribution_id, "user_id": user_id}
        )
        logger.info(
            "Goal contribution deleted",
            contribution_id=contribution_id,
            user_id=user_id,
        )


def _row_to_contribution(row: dict[str, Any]) -> GoalContribution:
    return GoalContribution(
        id=str(row["id"]),
        goal_id=str(row["goal_id"]),
        user_id=str(row["user_id"]),
        amount=_parse_decimal(row.get("amount")),
        contribution_date=_parse_date(row.get("contribution_date")),
        created_at=_parse_datetime(row.get("created_at")),
    )
