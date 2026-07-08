"""Supabase-backed goal repository (data access only)."""

from typing import Any

from app.core.exceptions import GoalNotFoundError, InfrastructureError
from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import (
    parse_datetime as _parse_datetime,
)
from app.shared.parsing import (
    parse_decimal as _parse_decimal,
)
from app.shared.parsing import (
    parse_enum as _parse_enum,
)
from app.shared.parsing import (
    parse_optional_date as _parse_optional_date,
)
from app.shared.parsing import (
    parse_optional_decimal as _parse_optional_decimal,
)
from app.shared.serialization import decimal_to_db
from app.shared.types import CurrencyType, GoalId, GoalStatus, GoalType, UserId

from ..constants import GOALS_TABLE
from ..interfaces import GoalRepositoryABC
from ..models import Goal, GoalCreate

logger = get_logger(__name__)


class GoalRepository(GoalRepositoryABC):
    """Persists goals in Supabase via the database interface."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def create(self, goal: GoalCreate, user_id: UserId) -> Goal:
        row = {
            "user_id": user_id,
            "name": goal.name,
            "description": goal.description,
            "type": goal.goal_type.value,
            "target_amount": decimal_to_db(goal.target_amount),
            "current_amount": decimal_to_db(goal.current_amount),
            "currency": goal.currency.value,
            "target_date": goal.target_date.isoformat() if goal.target_date else None,
            "status": GoalStatus.ACTIVE.value,
            "priority": goal.priority,
        }

        result = await self._db.insert(GOALS_TABLE, row)
        if not result.data:
            raise InfrastructureError(
                "Goal insert returned no rows", code="GOAL_INSERT_FAILED"
            )

        created = _row_to_goal(result.data[0])
        logger.info("Goal created", goal_id=created.id, user_id=user_id)
        return created

    async def get_by_id(self, goal_id: GoalId, user_id: UserId) -> Goal | None:
        config = QueryConfig(filters={"id": goal_id, "user_id": user_id}, limit=1)
        result = await self._db.select(GOALS_TABLE, config)
        if not result.data:
            return None
        return _row_to_goal(result.data[0])

    async def list_page(self, user_id: UserId, *, limit: int, offset: int) -> list[Goal]:
        config = QueryConfig(
            filters={"user_id": user_id},
            limit=limit,
            offset=offset,
            order_by="priority",
            order_ascending=True,
        )
        result = await self._db.select(GOALS_TABLE, config)
        return [_row_to_goal(row) for row in result.data]

    async def count(self, user_id: UserId) -> int:
        return await self._db.count(GOALS_TABLE, {"user_id": user_id})

    async def update(self, goal_id: GoalId, user_id: UserId, data: dict[str, Any]) -> Goal:
        result = await self._db.update(
            GOALS_TABLE, data, {"id": goal_id, "user_id": user_id}
        )
        if not result.data:
            raise GoalNotFoundError(goal_id)
        return _row_to_goal(result.data[0])

    async def delete(self, goal_id: GoalId, user_id: UserId) -> None:
        # Scoped by user_id so a user can only delete their own goals.
        await self._db.delete(GOALS_TABLE, {"id": goal_id, "user_id": user_id})


def _row_to_goal(row: dict[str, Any]) -> Goal:
    """Map a raw database row to a domain ``Goal``."""
    return Goal(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        name=row["name"],
        description=row.get("description"),
        goal_type=_parse_enum(GoalType, row.get("type"), GoalType.OTHER),
        target_amount=_parse_decimal(row.get("target_amount")),
        current_amount=_parse_decimal(row.get("current_amount")),
        currency=_parse_enum(CurrencyType, row.get("currency"), CurrencyType.MXN),
        target_date=_parse_optional_date(row.get("target_date")),
        monthly_contribution=_parse_optional_decimal(row.get("monthly_contribution")),
        status=_parse_enum(GoalStatus, row.get("status"), GoalStatus.ACTIVE),
        priority=int(row.get("priority", 1)),
        created_at=_parse_datetime(row.get("created_at")),
    )


