"""Transaction-related tools for agents."""

from datetime import date
from decimal import Decimal

from langchain_core.tools import tool

from app.core.logging import get_logger

logger = get_logger(__name__)


@tool
async def query_transactions(
    user_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Query user transactions with optional filters.

    Args:
        user_id: The user's ID.
        start_date: Start date for filtering.
        end_date: End date for filtering.
        category: Category to filter by.
        limit: Maximum number of transactions to return.

    Returns:
        List of transactions matching the criteria.
    """
    logger.info(
        "Querying transactions",
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        category=category,
    )

    # TODO: Implement actual database query
    return []


@tool
async def categorize_transaction(
    description: str,
    amount: Decimal,
) -> str:
    """Categorize a transaction using semantic similarity.

    Args:
        description: Transaction description.
        amount: Transaction amount.

    Returns:
        Suggested category.
    """
    logger.info(
        "Categorizing transaction",
        description=description[:50],
        amount=float(amount),
    )

    # TODO: Implement actual categorization with embeddings
    return "other"


@tool
async def get_transaction_summary(
    user_id: str,
    period: str = "month",
) -> dict:
    """Get a summary of transactions for a period.

    Args:
        user_id: The user's ID.
        period: Time period (day, week, month, quarter, year).

    Returns:
        Summary with totals by category and type.
    """
    logger.info(
        "Getting transaction summary",
        user_id=user_id,
        period=period,
    )

    # TODO: Implement actual summary calculation
    return {
        "period": period,
        "total_income": 0,
        "total_expenses": 0,
        "by_category": {},
        "transaction_count": 0,
    }
