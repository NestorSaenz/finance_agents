"""Goal-related tools for agents."""

from datetime import date
from decimal import Decimal

from langchain_core.tools import tool

from app.core.logging import get_logger

logger = get_logger(__name__)


@tool
async def create_goal(
    user_id: str,
    name: str,
    target_amount: Decimal,
    deadline: date | None = None,
) -> dict:
    """Create a new financial goal.

    Args:
        user_id: The user's ID.
        name: Name of the goal.
        target_amount: Target amount to save.
        deadline: Optional deadline for the goal.

    Returns:
        Created goal details.
    """
    logger.info(
        "Creating goal",
        user_id=user_id,
        name=name,
        target=float(target_amount),
    )

    # TODO: Implement actual goal creation
    return {
        "id": "goal_placeholder",
        "name": name,
        "target_amount": float(target_amount),
        "current_amount": 0,
        "deadline": str(deadline) if deadline else None,
        "status": "active",
    }


@tool
async def update_goal(
    goal_id: str,
    current_amount: Decimal | None = None,
    status: str | None = None,
) -> dict:
    """Update an existing goal.

    Args:
        goal_id: The goal's ID.
        current_amount: New current amount (if updating progress).
        status: New status (active, completed, cancelled).

    Returns:
        Updated goal details.
    """
    logger.info(
        "Updating goal",
        goal_id=goal_id,
        current_amount=float(current_amount) if current_amount else None,
        status=status,
    )

    # TODO: Implement actual goal update
    return {
        "id": goal_id,
        "updated": True,
    }


@tool
async def get_goal_progress(
    user_id: str,
    goal_id: str | None = None,
) -> list[dict]:
    """Get progress on financial goals.

    Args:
        user_id: The user's ID.
        goal_id: Optional specific goal ID.

    Returns:
        List of goals with progress information.
    """
    logger.info(
        "Getting goal progress",
        user_id=user_id,
        goal_id=goal_id,
    )

    # TODO: Implement actual goal progress retrieval
    return []
