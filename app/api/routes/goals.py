"""Goal endpoints: CRUD, contributions, and progress tracking."""

from datetime import date
from decimal import Decimal
from typing import Final

import httpx
from fastapi import APIRouter, Path, Query
from postgrest.exceptions import APIError

from app.core.config import settings
from app.core.exceptions import DatabaseError
from app.core.logging import get_logger
from app.shared.clock import local_today
from app.shared.periods import TODO, resolve_period
from app.shared.types import GoalPlanClearMode, UserId
from app.src.auth.dependencies import CurrentUserId
from app.src.goals.constants import DEFAULT_HISTORY_MONTHS, MAX_HISTORY_MONTHS
from app.src.goals.dependencies import GoalServiceDep
from app.src.goals.dto import (
    GoalContributeRequest,
    GoalContributionItem,
    GoalContributionsResponse,
    GoalCreateRequest,
    GoalListResponse,
    GoalMonthlyHistoryResponse,
    GoalPlanRequest,
    GoalPlanResponse,
    GoalPlanStatusListResponse,
    GoalProgressResponse,
    GoalResponse,
    GoalUpdateRequest,
)
from app.src.goals.models import GoalCreate
from app.src.goals.planning import month_key
from app.src.users.dependencies import UserProfileServiceDep

logger = get_logger(__name__)

router = APIRouter()

# A profile read that fails must not block a contribution: fall back to the app timezone.
_PROFILE_FAILURES: Final = (DatabaseError, APIError, httpx.HTTPError)

# A month as YYYY-MM (year 1000+, month 01-12) and the reporting periods that include it.
# No lookaheads: pydantic validates patterns with a regex engine that doesn't support them.
_MONTH_PATTERN: Final = r"^[1-9]\d{3}-(0[1-9]|1[0-2])$"
_PERIOD_PATTERN: Final = r"^(este_mes|mes_pasado|todo|[1-9]\d{3}-(0[1-9]|1[0-2]))$"


async def _user_today(profiles: UserProfileServiceDep, user_id: UserId) -> date:
    """Today on the USER's calendar (profile timezone), never the server's UTC day.

    Near midnight in Colombia the UTC date is already tomorrow, which would date an
    aporte made at 23:06 on the 30th as the 1st.
    """
    try:
        timezone = (await profiles.get_profile(user_id)).timezone
    except _PROFILE_FAILURES as e:
        logger.warning("Could not load profile timezone", user_id=user_id, error=str(e))
        timezone = None
    return local_today((timezone or "").strip() or settings.DEFAULT_TIMEZONE)


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


@router.get("/contributions", response_model=GoalContributionsResponse)
async def list_goal_contributions(
    service: GoalServiceDep,
    user_id: CurrentUserId,
    period: str = Query(
        default="este_mes",
        description="Reporting period: 'este_mes', 'mes_pasado', 'todo' or a month 'YYYY-MM'",
    ),
) -> GoalContributionsResponse:
    """List the goal contributions (aportes) made in the period (as events).

    Declared BEFORE ``/{goal_id}`` so the literal ``/contributions`` path isn't
    swallowed by the goal-id path parameter.
    """
    start, end = resolve_period(period)
    contributions = await service.list_contributions_in_period(user_id, start, end)
    return GoalContributionsResponse(
        contributions=[GoalContributionItem.from_domain(c) for c in contributions],
        total=sum((c.amount for c in contributions), Decimal("0")),
    )


@router.get("/plan-status", response_model=GoalPlanStatusListResponse)
async def get_goal_plan_status(
    service: GoalServiceDep,
    profiles: UserProfileServiceDep,
    user_id: CurrentUserId,
    period: str = Query(
        default="este_mes",
        pattern=_PERIOD_PATTERN,
        description="Month to evaluate: 'este_mes', 'mes_pasado', a month 'YYYY-MM' or "
        "'todo' (no plan block: returns an empty list)",
    ),
) -> GoalPlanStatusListResponse:
    """Plan vs contributed per goal for a month (totals grouped by currency).

    Declared BEFORE ``/{goal_id}`` so the literal ``/plan-status`` path isn't
    swallowed by the goal-id path parameter.
    """
    if period == TODO:
        return GoalPlanStatusListResponse.from_domain([])
    today = await _user_today(profiles, user_id)
    start, end = resolve_period(period, today)
    statuses = await service.get_plan_status(user_id, start, end, today)
    return GoalPlanStatusListResponse.from_domain(statuses)


@router.get("/monthly", response_model=GoalMonthlyHistoryResponse)
async def get_goal_monthly_history(
    service: GoalServiceDep,
    profiles: UserProfileServiceDep,
    user_id: CurrentUserId,
    months: int = Query(
        default=DEFAULT_HISTORY_MONTHS,
        ge=1,
        le=MAX_HISTORY_MONTHS,
        description="How many months before the chosen month to include (it is included too)",
    ),
    to: str | None = Query(
        default=None,
        pattern=_MONTH_PATTERN,
        description="Last month of the window as 'YYYY-MM'; defaults to the current month",
    ),
) -> GoalMonthlyHistoryResponse:
    """Month-by-month plan vs contributed per goal (future months only if planned).

    Declared BEFORE ``/{goal_id}`` (see ``/plan-status``).
    """
    today = await _user_today(profiles, user_id)
    to_month = resolve_period(to, today)[0] if to else None
    lines = await service.get_monthly_history(user_id, months, to_month, today)
    return GoalMonthlyHistoryResponse.from_domain(lines)


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
    profiles: UserProfileServiceDep,
    user_id: CurrentUserId,
) -> GoalProgressResponse:
    """Get a goal's progress, including the required monthly contribution."""
    progress = await service.get_progress(
        goal_id, user_id, as_of=await _user_today(profiles, user_id)
    )
    return GoalProgressResponse.from_domain(progress)


@router.post("/{goal_id}/contribute", response_model=GoalResponse)
async def contribute_to_goal(
    goal_id: str,
    request: GoalContributeRequest,
    service: GoalServiceDep,
    profiles: UserProfileServiceDep,
    user_id: CurrentUserId,
) -> GoalResponse:
    """Add an amount to a goal, completing it automatically when reached.

    Without a ``contribution_date`` the aporte is dated TODAY in the user's timezone.
    """
    contribution_date = request.contribution_date or await _user_today(profiles, user_id)
    goal = await service.contribute(goal_id, user_id, request.amount, contribution_date)
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


@router.put("/{goal_id}/plans/{month}", response_model=GoalPlanResponse)
async def set_goal_plan(
    goal_id: str,
    request: GoalPlanRequest,
    service: GoalServiceDep,
    user_id: CurrentUserId,
    month: str = Path(pattern=_MONTH_PATTERN, description="Month as YYYY-MM"),
) -> GoalPlanResponse:
    """Plan how much to save toward a goal in a month (only that month, or from it on)."""
    month_start = resolve_period(month)[0]
    planned = await service.set_plan(
        user_id, goal_id, request.amount, month_start, request.scope
    )
    return GoalPlanResponse(
        goal_id=goal_id, month=month_key(month_start), planned_amount=planned
    )


@router.delete("/{goal_id}/plans/{month}", response_model=GoalPlanResponse)
async def clear_goal_plan(
    goal_id: str,
    service: GoalServiceDep,
    user_id: CurrentUserId,
    month: str = Path(pattern=_MONTH_PATTERN, description="Month as YYYY-MM"),
    mode: GoalPlanClearMode = Query(
        default=GoalPlanClearMode.VOLVER_AL_GENERAL,
        description="'sin_plan' (don't plan this month), 'volver_al_general' (drop the "
        "month's own plan) or 'terminar' (stop planning from this month on)",
    ),
) -> GoalPlanResponse:
    """Clear a goal's plan for a month; returns the plan that applies afterwards."""
    month_start = resolve_period(month)[0]
    planned = await service.clear_plan(user_id, goal_id, month_start, mode)
    return GoalPlanResponse(
        goal_id=goal_id, month=month_key(month_start), planned_amount=planned
    )
