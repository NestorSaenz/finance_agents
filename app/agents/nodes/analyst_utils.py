"""Utility functions for the analyst agent.

Contains helper functions for transaction analysis calculations.
"""

from collections import defaultdict
from datetime import datetime

from app.agents.nodes.analyst_constants import (
    HIGH_SPENDING_THRESHOLD,
    MIN_TRANSACTIONS_FOR_PATTERNS,
    RECURRING_AMOUNT_TOLERANCE,
    RECURRING_MIN_OCCURRENCES,
    get_category_label,
)


def calculate_totals(transactions: list[dict]) -> tuple[float, float]:
    """Calculate total income and expenses.

    Args:
        transactions: List of transaction dictionaries.

    Returns:
        Tuple of (total_income, total_expenses).
    """
    total_income = 0.0
    total_expenses = 0.0

    for tx in transactions:
        amount = float(tx.get("amount", 0))
        tx_type = tx.get("transaction_type", "expense")

        if tx_type == "income":
            total_income += amount
        else:
            total_expenses += amount

    return total_income, total_expenses


def aggregate_by_category(transactions: list[dict]) -> dict[str, float]:
    """Aggregate expenses by category.

    Args:
        transactions: List of transaction dictionaries.

    Returns:
        Dictionary mapping category to total amount, sorted descending.
    """
    by_category: dict[str, float] = defaultdict(float)

    for tx in transactions:
        if tx.get("transaction_type") == "income":
            continue

        category = tx.get("category", "otros")
        amount = float(tx.get("amount", 0))
        by_category[category] += amount

    return dict(sorted(by_category.items(), key=lambda x: x[1], reverse=True))


def get_period_range(
    transactions: list[dict],
) -> tuple[datetime | None, datetime | None]:
    """Get the date range of transactions.

    Args:
        transactions: List of transaction dictionaries.

    Returns:
        Tuple of (start_date, end_date) or (None, None) if no dates.
    """
    dates = []
    for tx in transactions:
        date_str = tx.get("transaction_date") or tx.get("created_at")
        if date_str:
            try:
                if isinstance(date_str, str):
                    date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                else:
                    date = date_str
                dates.append(date)
            except (ValueError, TypeError):
                continue

    if not dates:
        return None, None

    return min(dates), max(dates)


def detect_patterns(
    transactions: list[dict],
    by_category: dict[str, float],
    total_expenses: float,
) -> list[str]:
    """Detect spending patterns.

    Args:
        transactions: List of transaction dictionaries.
        by_category: Aggregated expenses by category.
        total_expenses: Total expense amount.

    Returns:
        List of detected pattern descriptions.
    """
    patterns: list[str] = []

    if len(transactions) < MIN_TRANSACTIONS_FOR_PATTERNS:
        return patterns

    # Pattern 1: High spending categories
    if total_expenses > 0:
        for category, amount in by_category.items():
            percentage = amount / total_expenses
            if percentage >= HIGH_SPENDING_THRESHOLD:
                label = get_category_label(category)
                patterns.append(f"Alto gasto en {label}: {percentage:.0%} del total")

    # Pattern 2: Recurring transactions
    recurring = find_recurring_transactions(transactions)
    for desc, count, avg_amount in recurring:
        patterns.append(f"Gasto recurrente: {desc} (~${avg_amount:,.0f}, {count} veces)")

    # Pattern 3: Category concentration
    if len(by_category) >= 3:
        top_3_total = sum(list(by_category.values())[:3])
        if total_expenses > 0 and top_3_total / total_expenses > 0.8:
            top_cats = [get_category_label(c) for c in list(by_category.keys())[:3]]
            patterns.append(f"80% del gasto concentrado en: {', '.join(top_cats)}")

    return patterns[:5]


def top_expenses(
    transactions: list[dict], limit: int
) -> list[tuple[str, float, str]]:
    """Return the largest individual expenses as (description, amount, category).

    Surfaces concrete purchases (with their descriptions) so the analysis can be
    richer than category totals — e.g. "tu mayor gasto fue X". Income is excluded.

    Args:
        transactions: List of transaction dictionaries.
        limit: Maximum number of expenses to return.

    Returns:
        Up to ``limit`` (description, amount, category) tuples, largest first.
    """
    expenses = [
        (
            str(tx.get("description", "")).strip() or "(sin descripción)",
            amount,
            str(tx.get("category", "otros")),
        )
        for tx in transactions
        if tx.get("transaction_type") != "income"
        and (amount := float(tx.get("amount", 0))) > 0
    ]
    expenses.sort(key=lambda item: item[1], reverse=True)
    return expenses[:limit]


def find_recurring_transactions(
    transactions: list[dict],
) -> list[tuple[str, int, float]]:
    """Find recurring transactions by description similarity.

    Args:
        transactions: List of transaction dictionaries.

    Returns:
        List of (description, count, average_amount) tuples.
    """
    by_desc: dict[str, list[float]] = defaultdict(list)

    for tx in transactions:
        if tx.get("transaction_type") == "income":
            continue

        desc = tx.get("description", "").lower().strip()[:30]
        amount = float(tx.get("amount", 0))

        if desc and amount > 0:
            by_desc[desc].append(amount)

    recurring = []
    for desc, amounts in by_desc.items():
        if len(amounts) >= RECURRING_MIN_OCCURRENCES:
            avg = sum(amounts) / len(amounts)
            similar = all(
                abs(a - avg) / avg <= RECURRING_AMOUNT_TOLERANCE for a in amounts
            )
            if similar:
                recurring.append((desc.capitalize(), len(amounts), avg))

    recurring.sort(key=lambda x: x[1], reverse=True)
    return recurring[:3]


def parse_insights(response: str) -> list[str]:
    """Parse insights from LLM response.

    Args:
        response: Raw LLM response text.

    Returns:
        List of parsed insight strings.
    """
    insights = []
    for line in response.strip().split("\n"):
        line = line.strip()
        if line.startswith(("•", "-", "*", "·")):
            insight = line.lstrip("•-*· ").strip()
            if insight:
                insights.append(insight)
    return insights[:4]


def fallback_insights(
    by_category: dict[str, float],
    total_expenses: float,
    patterns: list[str],
) -> list[str]:
    """Generate basic insights without LLM.

    Args:
        by_category: Expenses aggregated by category.
        total_expenses: Total expense amount.
        patterns: Detected patterns.

    Returns:
        List of fallback insight strings.
    """
    insights = []

    if by_category:
        top_cat = list(by_category.keys())[0]
        top_amount = by_category[top_cat]
        label = get_category_label(top_cat)
        insights.append(f"Tu mayor gasto es en {label} (${top_amount:,.0f})")

    if len(patterns) > 0:
        insights.append("Se detectaron patrones de gasto recurrente")

    if total_expenses > 0:
        insights.append("Revisa tus gastos para identificar oportunidades de ahorro")

    return insights
