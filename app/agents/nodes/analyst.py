"""Analyst agent node.

The analyst detects spending patterns, generates insights,
and provides financial metrics based on user transaction data.
"""

from datetime import datetime

from app.agents.models import AnalysisResult
from app.agents.nodes.analyst_constants import (
    INSIGHT_GENERATION_PROMPT,
    INSIGHT_SYSTEM_PROMPT,
    get_category_label,
)
from app.agents.nodes.analyst_utils import (
    aggregate_by_category,
    calculate_totals,
    detect_patterns,
    fallback_insights,
    get_period_range,
    parse_insights,
)
from app.agents.state import AgentState
from app.agents.types import AgentName
from app.core.logging import get_logger
from app.shared.interfaces.llm import LLMConfig, LLMInterface, Message, MessageRole

logger = get_logger(__name__)


async def analyst_node(
    state: AgentState,
    llm: LLMInterface,
) -> AgentState:
    """Analyze user's financial data and generate insights.

    Performs:
    1. Aggregation by category and time period
    2. Pattern detection (recurring expenses, trends)
    3. LLM-powered insight generation

    Args:
        state: Current agent state with user context and transactions.
        llm: LLM client for insight generation.

    Returns:
        Updated state with analysis results.
    """
    user_id = state.get("user_id", "unknown")
    transactions = state.get("recent_transactions", [])

    logger.info("Analyst processing", user_id=user_id, tx_count=len(transactions))

    if not transactions:
        logger.warning("No transactions available for analysis")
        return {
            **state,
            "analysis_results": _empty_analysis(),
            "should_respond": True,
            "next_agent": AgentName.RESPONSE_GENERATOR.value,
        }

    # Perform analysis
    analysis = await _analyze_transactions(transactions, llm)

    logger.info(
        "Analysis completed",
        total_expenses=analysis.total_expenses,
        categories=len(analysis.by_category),
        patterns=len(analysis.patterns),
        insights=len(analysis.insights),
    )

    return {
        **state,
        "analysis_results": analysis.model_dump(),
        "should_respond": True,
        "next_agent": AgentName.RESPONSE_GENERATOR.value,
    }


async def _analyze_transactions(
    transactions: list[dict],
    llm: LLMInterface,
) -> AnalysisResult:
    """Perform comprehensive transaction analysis."""
    total_income, total_expenses = calculate_totals(transactions)
    by_category = aggregate_by_category(transactions)
    period_start, period_end = get_period_range(transactions)
    patterns = detect_patterns(transactions, by_category, total_expenses)

    insights = await _generate_insights(
        llm=llm,
        total_income=total_income,
        total_expenses=total_expenses,
        by_category=by_category,
        patterns=patterns,
        period_start=period_start,
        period_end=period_end,
    )

    return AnalysisResult(
        period_start=period_start,
        period_end=period_end,
        total_income=total_income,
        total_expenses=total_expenses,
        by_category=by_category,
        patterns=patterns,
        insights=insights,
    )


async def _generate_insights(
    llm: LLMInterface,
    total_income: float,
    total_expenses: float,
    by_category: dict[str, float],
    patterns: list[str],
    period_start: datetime | None,
    period_end: datetime | None,
) -> list[str]:
    """Generate insights using LLM."""
    if period_start and period_end:
        period = f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}"
    else:
        period = "Período no determinado"

    balance = total_income - total_expenses
    balance_pct = (balance / total_income * 100) if total_income > 0 else 0

    cat_lines = []
    for cat, amount in list(by_category.items())[:6]:
        pct = (amount / total_expenses * 100) if total_expenses > 0 else 0
        label = get_category_label(cat)
        cat_lines.append(f"  • {label}: ${amount:,.2f} ({pct:.1f}%)")
    category_breakdown = "\n".join(cat_lines) if cat_lines else "  Sin datos"

    patterns_str = "\n".join(f"  • {p}" for p in patterns) if patterns else "  Ninguno"

    prompt = INSIGHT_GENERATION_PROMPT.format(
        period=period,
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance,
        balance_percentage=balance_pct,
        category_breakdown=category_breakdown,
        patterns=patterns_str,
        comparison="Sin datos de período anterior",
    )

    try:
        config = LLMConfig(temperature=0.7, max_tokens=300)
        response = await llm.generate(
            messages=[
                Message(role=MessageRole.SYSTEM, content=INSIGHT_SYSTEM_PROMPT),
                Message(role=MessageRole.USER, content=prompt),
            ],
            config=config,
        )
        return parse_insights(response.content)

    except Exception as e:
        logger.error("Failed to generate insights", error=str(e))
        return fallback_insights(by_category, total_expenses, patterns)


def _empty_analysis() -> dict:
    """Return empty analysis result."""
    return AnalysisResult(
        total_income=0.0,
        total_expenses=0.0,
        by_category={},
        patterns=["No hay transacciones para analizar"],
        insights=["Registra tus primeras transacciones para obtener insights"],
    ).model_dump()
