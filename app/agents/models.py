"""Domain models for the multiagent system.

This module defines Pydantic models for agent state, plans,
and classification results.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.agents.types import AgentName, Complexity, Intent, PlanStepStatus


class PlanStep(BaseModel):
    """Represents a single step in a complex query plan.

    Used in the Plan-Execute-Replan cycle for complex queries.
    """

    step_number: int = Field(..., ge=1, description="Step number in the plan")
    description: str = Field(..., min_length=1, description="What this step does")
    assigned_agent: AgentName = Field(..., description="Agent responsible for this step")
    status: PlanStepStatus = Field(
        default=PlanStepStatus.PENDING,
        description="Current status of the step",
    )
    result: dict[str, Any] | None = Field(
        default=None,
        description="Result data from step execution",
    )
    error: str | None = Field(
        default=None,
        description="Error message if step failed",
    )

    class Config:
        use_enum_values = True


class ClassificationResult(BaseModel):
    """Result of query classification.

    Contains both intent and complexity analysis.
    """

    intent: Intent = Field(..., description="Detected user intent")
    complexity: Complexity = Field(..., description="Query complexity level")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Classification confidence score",
    )
    next_agent: AgentName = Field(..., description="Next agent to route to")

    class Config:
        use_enum_values = True


class ExecutionResult(BaseModel):
    """Result of a plan step execution."""

    step_number: int = Field(..., ge=1)
    success: bool = Field(..., description="Whether execution succeeded")
    data: dict[str, Any] = Field(default_factory=dict, description="Result data")
    error: str | None = Field(default=None, description="Error if failed")
    duration_ms: int = Field(default=0, ge=0, description="Execution time in ms")


class AgentResponse(BaseModel):
    """Standard response from any agent node."""

    agent_name: AgentName
    success: bool = True
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    next_agent: AgentName | None = None
    should_respond: bool = False

    class Config:
        use_enum_values = True


class ConversationContext(BaseModel):
    """Context for the current conversation."""

    user_id: str = Field(..., description="User identifier")
    session_id: str | None = Field(default=None, description="Session identifier")
    language: str = Field(default="es", description="User language preference")
    timezone: str = Field(default="America/Mexico_City", description="User timezone")


class FinancialContext(BaseModel):
    """Financial data context for agents."""

    recent_transactions: list[dict[str, Any]] = Field(default_factory=list)
    current_budgets: list[dict[str, Any]] = Field(default_factory=list)
    active_goals: list[dict[str, Any]] = Field(default_factory=list)
    total_balance: float | None = None
    monthly_income: float | None = None
    monthly_expenses: float | None = None


class AnalysisResult(BaseModel):
    """Result from the Analyst agent."""

    period_start: datetime | None = None
    period_end: datetime | None = None
    total_income: float = 0.0
    total_expenses: float = 0.0
    by_category: dict[str, float] = Field(default_factory=dict)
    patterns: list[str] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)


class CategorySuggestion(BaseModel):
    """Result from the Categorizer agent."""

    category: str = Field(..., description="Suggested category")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the suggestion",
    )
    alternatives: list[str] = Field(
        default_factory=list,
        description="Alternative category suggestions",
    )


class SavingsPlan(BaseModel):
    """Result from the Planner agent."""

    goal_name: str
    target_amount: float
    current_amount: float = 0.0
    monthly_contribution: float
    estimated_completion: datetime | None = None
    recommendations: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """A single recommendation from the Recommender agent."""

    title: str
    description: str
    potential_savings: float | None = None
    priority: int = Field(default=1, ge=1, le=5)
    category: str | None = None
