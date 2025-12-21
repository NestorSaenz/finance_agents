"""Agent state definitions for LangGraph."""

from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages


class PlanStep(TypedDict):
    """Represents a single step in a plan."""

    step_number: int
    description: str
    assigned_agent: str
    status: Literal["pending", "in_progress", "completed", "failed"]
    result: dict | None
    error: str | None


class AgentState(TypedDict):
    """Shared state between all agents in the graph.

    This state flows through all nodes and is used to coordinate
    the multiagent system.
    """

    # Conversation messages
    messages: Annotated[list, add_messages]

    # User context
    user_id: str
    user_preferences: dict

    # Relevant financial data
    recent_transactions: list[dict]
    current_budgets: list[dict]
    active_goals: list[dict]

    # Query classification
    detected_intent: str
    query_complexity: Literal["simple", "complex"]

    # Plan-Execute-Replan (complex path only)
    current_plan: list[PlanStep]
    current_step_index: int
    execution_history: list[dict]
    requires_replan: bool

    # Intermediate results
    category_suggestion: str | None
    analysis_results: dict | None
    recommendations: list[str]

    # Flow control
    next_agent: str
    should_respond: bool
    iteration_count: int
    max_iterations: int
