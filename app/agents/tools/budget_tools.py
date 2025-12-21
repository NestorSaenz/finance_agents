"""Budget-related tools for agents."""

from decimal import Decimal

from langchain_core.tools import tool

from app.core.logging import get_logger

logger = get_logger(__name__)


@tool
async def create_budget(
    user_id: str,
    category: str,
    amount_limit: Decimal,
    period: str = "monthly",
    alert_threshold: float = 0.8,
) -> dict:
    """Create a new budget for a category.

    Args:
        user_id: The user's ID.
        category: Category for the budget.
        amount_limit: Maximum amount for the period.
        period: Budget period (weekly, monthly, quarterly).
        alert_threshold: Percentage at which to alert (0-1).

    Returns:
        Created budget details.
    """
    logger.info(
        "Creating budget",
        user_id=user_id,
        category=category,
        limit=float(amount_limit),
    )

    # TODO: Implement actual budget creation
    return {
        "id": "budget_placeholder",
        "category": category,
        "amount_limit": float(amount_limit),
        "period": period,
        "alert_threshold": alert_threshold,
    }


@tool
async def check_budget_status(
    user_id: str,
    category: str | None = None,
) -> list[dict]:
    """Check the status of user's budgets.

    Args:
        user_id: The user's ID.
        category: Optional category to filter.

    Returns:
        List of budget statuses with current spending.
    """
    logger.info(
        "Checking budget status",
        user_id=user_id,
        category=category,
    )

    # TODO: Implement actual budget status check
    return []


@tool
async def get_budget_alerts(
    user_id: str,
) -> list[dict]:
    """Get budget alerts for the user.

    Args:
        user_id: The user's ID.

    Returns:
        List of budget alerts (exceeded or near threshold).
    """
    logger.info("Getting budget alerts", user_id=user_id)

    # TODO: Implement actual alert checking
    return []
