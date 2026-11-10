"""Supabase-backed goal-plan repository (data access only)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.core.exceptions import InfrastructureError
from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import parse_date as _parse_date
from app.shared.parsing import parse_decimal as _parse_decimal
from app.shared.serialization import decimal_to_db
from app.shared.types import GoalId, GoalPlanKind, UserId

from ..constants import GOAL_PLANS_CONFLICT, GOAL_PLANS_TABLE
from ..interfaces import GoalPlanRepositoryABC
from ..models import GoalPlan

logger = get_logger(__name__)


class GoalPlanRepository(GoalPlanRepositoryABC):
    """Persists goal savings plans in Supabase."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def list_for_user(self, user_id: UserId) -> list[GoalPlan]:
        config = QueryConfig(
            filters={"user_id": user_id}, order_by="month", order_ascending=True
        )
        result = await self._db.select(GOAL_PLANS_TABLE, config)
        return [_row_to_plan(row) for row in result.data]

    async def list_for_goal(self, user_id: UserId, goal_id: GoalId) -> list[GoalPlan]:
        config = QueryConfig(
            filters={"user_id": user_id, "goal_id": goal_id},
            order_by="month",
            order_ascending=True,
        )
        result = await self._db.select(GOAL_PLANS_TABLE, config)
        return [_row_to_plan(row) for row in result.data]

    async def upsert(
        self,
        user_id: UserId,
        goal_id: GoalId,
        month: date,
        kind: GoalPlanKind,
        amount: Decimal,
    ) -> GoalPlan:
        row = {
            "user_id": user_id,
            "goal_id": goal_id,
            "month": month.isoformat(),
            "kind": kind.value,
            "planned_amount": decimal_to_db(amount),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        result = await self._db.upsert(GOAL_PLANS_TABLE, row, GOAL_PLANS_CONFLICT)
        if not result.data:
            raise InfrastructureError(
                "Goal plan upsert returned no rows", code="GOAL_PLAN_UPSERT_FAILED"
            )
        plan = _row_to_plan(result.data[0])
        logger.info(
            "Goal plan saved", goal_id=goal_id, user_id=user_id, kind=kind.value
        )
        return plan

    async def delete(
        self, user_id: UserId, goal_id: GoalId, month: date, kind: GoalPlanKind
    ) -> None:
        await self._db.delete(
            GOAL_PLANS_TABLE,
            {
                "user_id": user_id,
                "goal_id": goal_id,
                "month": month.isoformat(),
                "kind": kind.value,
            },
        )
        logger.info(
            "Goal plan deleted", goal_id=goal_id, user_id=user_id, kind=kind.value
        )


def _row_to_plan(row: dict[str, Any]) -> GoalPlan:
    """Map a raw database row to a domain ``GoalPlan``."""
    try:
        kind = GoalPlanKind(str(row.get("kind")))
    except ValueError as e:
        logger.error("Unknown goal plan kind", plan_id=row.get("id"), kind=row.get("kind"))
        raise InfrastructureError(
            f"Unknown goal plan kind: {row.get('kind')!r}", code="GOAL_PLAN_INVALID_KIND"
        ) from e
    return GoalPlan(
        id=str(row["id"]),
        goal_id=str(row["goal_id"]),
        user_id=str(row["user_id"]),
        month=_parse_date(row.get("month")),
        planned_amount=_parse_decimal(row.get("planned_amount")),
        kind=kind,
    )
