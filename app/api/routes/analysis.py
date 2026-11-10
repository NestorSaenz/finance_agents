"""Analysis endpoints: cross-module financial aggregations (read-only)."""

from typing import Final

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.logging import get_logger
from app.shared.periods import ESTE_MES, resolve_period
from app.src.analysis.dependencies import AnalysisServiceDep
from app.src.analysis.dto import AccumulatedSurplusResponse, PeriodSpendingResponse
from app.src.auth.dependencies import CurrentUserId

logger = get_logger(__name__)

# A reporting period: a named one or a month as YYYY-MM (year 1000+).
_PERIOD_PATTERN: Final = r"^(este_mes|mes_pasado|todo|[1-9]\d{3}-(0[1-9]|1[0-2]))$"

router = APIRouter()


@router.get("/excedente", response_model=AccumulatedSurplusResponse)
async def get_accumulated_surplus(
    service: AnalysisServiceDep,
    user_id: CurrentUserId,
    period: str = Query(
        default=ESTE_MES,
        description="Reporting period (e.g. 'este_mes' or 'YYYY-MM'); the surplus "
        "is accumulated up to that month-end.",
    ),
) -> AccumulatedSurplusResponse:
    """Return the user's accumulated surplus (free cash) as of the period's month-end."""
    as_of = resolve_period(period)[1]
    surplus = await service.accumulated_surplus(user_id, as_of)
    return AccumulatedSurplusResponse(accumulated_surplus=surplus)


@router.get("/summary", response_model=PeriodSpendingResponse)
async def get_period_spending(
    service: AnalysisServiceDep,
    user_id: CurrentUserId,
    period: str = Query(
        default=ESTE_MES,
        pattern=_PERIOD_PATTERN,
        description="Reporting period: 'este_mes', 'mes_pasado', 'todo' or a month 'YYYY-MM'",
    ),
) -> PeriodSpendingResponse:
    """Consumption (as /transactions/summary) plus the money set aside into goals.

    ``total_expenses`` stays consumption; ``total_spent`` and ``balance`` include the goal
    contributions dated on/after ``goal_spending_from``.
    """
    start, end = resolve_period(period)
    spending = await service.period_spending(user_id, start, end)
    return PeriodSpendingResponse.from_domain(
        spending, period, settings.GOALS_COUNT_AS_SPENDING_FROM
    )
