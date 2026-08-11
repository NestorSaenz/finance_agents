"""Analysis endpoints: cross-module financial aggregations (read-only)."""

from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.shared.periods import ESTE_MES, resolve_period
from app.src.analysis.dependencies import AnalysisServiceDep
from app.src.analysis.dto import AccumulatedSurplusResponse
from app.src.auth.dependencies import CurrentUserId

logger = get_logger(__name__)

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
