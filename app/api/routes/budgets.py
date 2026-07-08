"""Budget endpoints: CRUD, status against spending, and active alerts."""

from decimal import Decimal

from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.src.auth.dependencies import CurrentUserId
from app.src.budgets.dependencies import BudgetServiceDep
from app.src.budgets.dto import (
    BudgetAlertsResponse,
    BudgetCreateRequest,
    BudgetListResponse,
    BudgetResponse,
    BudgetStatusListResponse,
    BudgetStatusResponse,
)
from app.src.budgets.models import BudgetCreate

logger = get_logger(__name__)

router = APIRouter()


@router.post("", response_model=BudgetResponse)
async def create_budget(
    request: BudgetCreateRequest,
    service: BudgetServiceDep,
    user_id: CurrentUserId,
) -> BudgetResponse:
    """Create a new budget."""
    budget = BudgetCreate(**request.model_dump())
    created = await service.create_budget(budget, user_id)
    return BudgetResponse.from_domain(created)


@router.get("", response_model=BudgetListResponse)
async def list_budgets(
    service: BudgetServiceDep,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
) -> BudgetListResponse:
    """List the current user's budgets."""
    items, total = await service.list_budgets(user_id, page=page, page_size=page_size)
    return BudgetListResponse(
        budgets=[BudgetResponse.from_domain(b) for b in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/alerts", response_model=BudgetAlertsResponse)
async def get_budget_alerts(
    service: BudgetServiceDep,
    user_id: CurrentUserId,
) -> BudgetAlertsResponse:
    """Return budgets whose alert threshold has been reached this period."""
    alerts = await service.get_active_alerts(user_id)
    return BudgetAlertsResponse(
        alerts=[BudgetStatusResponse.from_domain(s) for s in alerts],
        count=len(alerts),
    )


@router.get("/status", response_model=BudgetStatusListResponse)
async def get_all_budget_status(
    service: BudgetServiceDep,
    user_id: CurrentUserId,
) -> BudgetStatusListResponse:
    """Return every active budget with spent-vs-limit (dashboard progress bars)."""
    statuses = await service.get_all_status(user_id)
    return BudgetStatusListResponse(
        statuses=[BudgetStatusResponse.from_domain(s) for s in statuses],
        total_budgeted=sum((s.budget.amount for s in statuses), Decimal("0")),
        total_spent=sum((s.spent for s in statuses), Decimal("0")),
    )


@router.get("/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: str,
    service: BudgetServiceDep,
    user_id: CurrentUserId,
) -> BudgetResponse:
    """Get a specific budget by id (404 if it does not exist)."""
    budget = await service.get_budget(budget_id, user_id)
    return BudgetResponse.from_domain(budget)


@router.get("/{budget_id}/status", response_model=BudgetStatusResponse)
async def get_budget_status(
    budget_id: str,
    service: BudgetServiceDep,
    user_id: CurrentUserId,
) -> BudgetStatusResponse:
    """Get a budget evaluated against actual spending in the current period."""
    status = await service.get_budget_status(budget_id, user_id)
    return BudgetStatusResponse.from_domain(status)
