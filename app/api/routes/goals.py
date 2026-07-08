"""Goal endpoints: CRUD, contributions, and progress tracking."""

from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.src.auth.dependencies import CurrentUserId
from app.src.goals.dependencies import GoalServiceDep
from app.src.goals.dto import (
    GoalContributeRequest,
    GoalCreateRequest,
    GoalListResponse,
    GoalProgressResponse,
    GoalResponse,
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
) -> GoalListResponse:
    """List the current user's goals (highest priority first)."""
    items, total = await service.list_goals(user_id, page=page, page_size=page_size)
    return GoalListResponse(
        goals=[GoalResponse.from_domain(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
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
    goal = await service.contribute(goal_id, user_id, request.amount)
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
