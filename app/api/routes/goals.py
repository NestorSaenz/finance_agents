"""Goal endpoints: CRUD, contributions, and progress tracking."""

from decimal import Decimal

from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.shared.periods import resolve_period
from app.src.auth.dependencies import CurrentUserId
from app.src.goals.dependencies import GoalServiceDep
from app.src.goals.dto import (
    GoalContributeRequest,
    GoalCreateRequest,
    GoalListResponse,
    GoalProgressResponse,
    GoalResponse,
    GoalUpdateRequest,
)
from app.src.goals.models import GoalCreate

logger = get_logger(__name__)

router = APIRouter()


@router.post("", response_model=GoalResponse)
async def create_goal(
    request: GoalCreateRequest,
    service: GoalServiceDep,
    user_id: CurrentUserId,
) -> GoalResponse:
    """Create a new financial goal."""
    goal = GoalCreate(**request.model_dump())
    created = await service.create_goal(goal, user_id)
    return GoalResponse.from_domain(created)


@router.get("", response_model=GoalListResponse)
async def list_goals(
    service: GoalServiceDep,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    period: str | None = Query(
        default=None,
        description="Reporting period (e.g. 'este_mes' or 'YYYY-MM'); goals then "
        "reflect their cumulative progress up to that month-end.",
    ),
) -> GoalListResponse:
    """List the current user's goals (highest priority first)."""
    # A period reconstructs each goal's progress at that month-end; without one,
    # the goal shows its live running total. With a period, also report how much
    # was set aside toward goals within it, so the dashboard's cash-flow view can
    # subtract it from disposable income.
    period_range = resolve_period(period) if period else None
    as_of = period_range[1] if period_range else None
    items, total = await service.list_goals(
        user_id, page=page, page_size=page_size, as_of=as_of
    )
    total_contributed = (
        await service.contributed_in_period(user_id, *period_range)
        if period_range
        else Decimal("0")
    )
    return GoalListResponse(
        goals=[GoalResponse.from_domain(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
        total_contributed=total_contributed,
    )


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: str,
    service: GoalServiceDep,
    user_id: CurrentUserId,
) -> GoalResponse:
    """Get a specific goal by id (404 if it does not exist)."""
    goal = await service.get_goal(goal_id, user_id)
    return GoalResponse.from_domain(goal)


@router.get("/{goal_id}/progress", response_model=GoalProgressResponse)
async def get_goal_progress(
    goal_id: str,
    service: GoalServiceDep,
    user_id: CurrentUserId,
) -> GoalProgressResponse:
    """Get a goal's progress, including the required monthly contribution."""
    progress = await service.get_progress(goal_id, user_id)
    return GoalProgressResponse.from_domain(progress)


@router.post("/{goal_id}/contribute", response_model=GoalResponse)
async def contribute_to_goal(
    goal_id: str,
    request: GoalContributeRequest,
    service: GoalServiceDep,
    user_id: CurrentUserId,
) -> GoalResponse:
    """Add an amount to a goal, completing it automatically when reached."""
    goal = await service.contribute(
        goal_id, user_id, request.amount, request.contribution_date
    )
    return GoalResponse.from_domain(goal)


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: str,
    request: GoalUpdateRequest,
    service: GoalServiceDep,
    user_id: CurrentUserId,
) -> GoalResponse:
    """Update a goal's name/target/date (404 if it does not exist)."""
    goal = await service.update_goal(
        goal_id,
        user_id,
        name=request.name,
        target_amount=request.target_amount,
        target_date=request.target_date,
    )
    return GoalResponse.from_domain(goal)


@router.delete("/{goal_id}", response_model=GoalResponse)
async def delete_goal(
    goal_id: str,
    service: GoalServiceDep,
    user_id: CurrentUserId,
) -> GoalResponse:
    """Delete a goal and return the removed goal (404 if it does not exist)."""
    goal = await service.delete_goal(goal_id, user_id)
    return GoalResponse.from_domain(goal)
