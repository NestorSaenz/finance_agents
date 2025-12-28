"""Data Transfer Objects for the agent API.

This module defines request/response schemas for agent-related
API endpoints, decoupled from internal domain models.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Chat Request/Response DTOs
# =============================================================================


class ChatMessageRequest(BaseModel):
    """Request to send a chat message."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="User message",
        examples=["Cuanto gaste en comida este mes?"],
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session ID for conversation continuity",
    )


class ChatMessageResponse(BaseModel):
    """Response from the chat agent."""

    message: str = Field(..., description="Agent response message")
    session_id: str = Field(..., description="Session ID for this conversation")
    intent: str = Field(..., description="Detected intent")
    complexity: str = Field(..., description="Query complexity (simple/complex)")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")


# =============================================================================
# Classification DTOs
# =============================================================================


class ClassifyRequest(BaseModel):
    """Request to classify a message."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Message to classify",
    )


class ClassifyResponse(BaseModel):
    """Classification result."""

    intent: str = Field(..., description="Detected intent type")
    complexity: str = Field(..., description="simple or complex")
    confidence: float = Field(..., description="Classification confidence")
    next_agent: str = Field(..., description="Suggested next agent")


# =============================================================================
# Categorization DTOs
# =============================================================================


class CategorizeRequest(BaseModel):
    """Request to categorize a transaction."""

    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Transaction description",
        examples=["Uber al trabajo"],
    )
    amount: float | None = Field(
        default=None,
        gt=0,
        description="Transaction amount for context",
    )


class CategorizeResponse(BaseModel):
    """Categorization result."""

    category: str = Field(..., description="Suggested category")
    confidence: float = Field(..., description="Confidence score 0-1")
    alternatives: list[str] = Field(
        default_factory=list,
        description="Alternative categories",
    )


# =============================================================================
# Analysis DTOs
# =============================================================================


class AnalysisRequest(BaseModel):
    """Request for spending analysis."""

    period_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Number of days to analyze",
    )
    categories: list[str] | None = Field(
        default=None,
        description="Filter by specific categories",
    )


class AnalysisResponse(BaseModel):
    """Spending analysis result."""

    period_start: datetime
    period_end: datetime
    total_income: float
    total_expenses: float
    net_balance: float
    by_category: dict[str, float]
    top_expenses: list[dict[str, Any]]
    patterns: list[str]
    insights: list[str]


# =============================================================================
# Planning DTOs
# =============================================================================


class SavingsPlanRequest(BaseModel):
    """Request to create a savings plan."""

    goal_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name of the savings goal",
        examples=["Viaje a Europa"],
    )
    target_amount: float = Field(
        ...,
        gt=0,
        description="Target amount to save",
    )
    deadline_months: int | None = Field(
        default=None,
        ge=1,
        le=120,
        description="Deadline in months",
    )


class SavingsPlanResponse(BaseModel):
    """Savings plan result."""

    goal_name: str
    target_amount: float
    current_amount: float
    monthly_contribution: float
    estimated_completion: datetime | None
    recommendations: list[str]
    feasibility_score: float = Field(
        ...,
        ge=0,
        le=1,
        description="How feasible is this plan based on current spending",
    )


# =============================================================================
# Recommendation DTOs
# =============================================================================


class RecommendationResponse(BaseModel):
    """A single recommendation."""

    title: str
    description: str
    potential_savings: float | None
    priority: int = Field(..., ge=1, le=5)
    category: str | None


class RecommendationsListResponse(BaseModel):
    """List of recommendations."""

    recommendations: list[RecommendationResponse]
    total_potential_savings: float
    generated_at: datetime


# =============================================================================
# Plan Execution DTOs (Complex Path)
# =============================================================================


class PlanStepResponse(BaseModel):
    """A step in the execution plan."""

    step_number: int
    description: str
    assigned_agent: str
    status: str
    result_summary: str | None = None


class ExecutionPlanResponse(BaseModel):
    """Full execution plan response."""

    query: str
    total_steps: int
    completed_steps: int
    current_step: int
    steps: list[PlanStepResponse]
    status: str = Field(
        ...,
        description="overall status: planning, executing, completed, failed",
    )
