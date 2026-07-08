"""Supabase-backed budget repository (data access only)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.exceptions import InfrastructureError
from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface, QueryConfig
from app.shared.parsing import (
    parse_date as _parse_date,
)
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
from app.shared.serialization import decimal_to_db
from app.shared.types import BudgetId, BudgetPeriod, CurrencyType, UserId

from ..constants import BUDGETS_TABLE
from ..interfaces import BudgetRepositoryABC
from ..models import Budget, BudgetCreate

logger = get_logger(__name__)


class BudgetRepository(BudgetRepositoryABC):
    """Persists budgets in Supabase via the database interface."""

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def create(self, budget: BudgetCreate, user_id: UserId) -> Budget:
        row = {
            "user_id": user_id,
            "name": budget.name,
            "amount": decimal_to_db(budget.amount),
            "currency": budget.currency.value,
            "category": budget.category if budget.category else None,
            "period_type": budget.period_type.value,
            "start_date": budget.start_date.isoformat(),
            "alert_threshold": decimal_to_db(budget.alert_threshold),
            "alert_enabled": budget.alert_enabled,
            "is_active": True,
        }

        result = await self._db.insert(BUDGETS_TABLE, row)
        if not result.data:
            raise InfrastructureError(
                "Budget insert returned no rows",
                code="BUDGET_INSERT_FAILED",
            )

        created = _row_to_budget(result.data[0])
        logger.info("Budget created", budget_id=created.id, user_id=user_id)
        return created

    async def get_by_id(self, budget_id: BudgetId, user_id: UserId) -> Budget | None:
        config = QueryConfig(filters={"id": budget_id, "user_id": user_id}, limit=1)
        result = await self._db.select(BUDGETS_TABLE, config)
        if not result.data:
            return None
        return _row_to_budget(result.data[0])

    async def list_page(self, user_id: UserId, *, limit: int, offset: int) -> list[Budget]:
        config = QueryConfig(
            filters={"user_id": user_id},
            limit=limit,
            offset=offset,
            order_by="created_at",
            order_ascending=False,
        )
        result = await self._db.select(BUDGETS_TABLE, config)
        return [_row_to_budget(row) for row in result.data]

    async def count(self, user_id: UserId) -> int:
        return await self._db.count(BUDGETS_TABLE, {"user_id": user_id})

    async def list_active(self, user_id: UserId) -> list[Budget]:
        config = QueryConfig(filters={"user_id": user_id, "is_active": True})
        result = await self._db.select(BUDGETS_TABLE, config)
        return [_row_to_budget(row) for row in result.data]

    async def update(
        self,
        budget_id: BudgetId,
        user_id: UserId,
        *,
        name: str | None = None,
        amount: Decimal | None = None,
    ) -> Budget | None:
        changes: dict[str, Any] = {}
        if name is not None:
            changes["name"] = name
        if amount is not None:
            changes["amount"] = decimal_to_db(amount)
        if not changes:
            return await self.get_by_id(budget_id, user_id)

        result = await self._db.update(
            BUDGETS_TABLE, changes, {"id": budget_id, "user_id": user_id}
        )
        if not result.data:
            return None
        updated = _row_to_budget(result.data[0])
        logger.info("Budget updated", budget_id=budget_id, user_id=user_id)
        return updated

    async def delete(self, budget_id: BudgetId, user_id: UserId) -> Budget | None:
        result = await self._db.delete(BUDGETS_TABLE, {"id": budget_id, "user_id": user_id})
        if not result.data:
            return None
        deleted = _row_to_budget(result.data[0])
        logger.info("Budget deleted", budget_id=budget_id, user_id=user_id)
        return deleted


def _row_to_budget(row: dict[str, Any]) -> Budget:
    """Map a raw database row to a domain ``Budget``."""
    return Budget(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        name=row["name"],
        amount=_parse_decimal(row.get("amount")),
        category=_parse_category(row.get("category")),
        currency=_parse_enum(CurrencyType, row.get("currency"), CurrencyType.MXN),
        period_type=_parse_enum(BudgetPeriod, row.get("period_type"), BudgetPeriod.MONTHLY),
        start_date=_parse_date(row.get("start_date")),
        end_date=_parse_optional_date(row.get("end_date")),
        alert_threshold=_parse_decimal(row.get("alert_threshold"), default=Decimal("80")),
        alert_enabled=bool(row.get("alert_enabled", True)),
        is_active=bool(row.get("is_active", True)),
        created_at=_parse_datetime(row.get("created_at")),
    )


def _parse_category(value: object) -> str | None:
    """Budget category: ``None`` means an overall (all-category) budget.

    Custom (non-enum) categories are preserved as stored; only NULL means overall.
    """
    return None if value is None else str(value)
