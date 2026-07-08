"""Domain models for the multiagent system."""

from pydantic import BaseModel, Field

from app.agents.types import AgentName, Intent


class ClassificationResult(BaseModel):
    """Result of intent classification (routes to a single agent)."""

    intent: Intent = Field(..., description="Detected user intent")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    next_agent: AgentName = Field(..., description="Next agent to route to")


class CategorySuggestion(BaseModel):
    """Result from the categorizer agent."""

    category: str = Field(..., description="Suggested category")
    confidence: float = Field(..., ge=0.0, le=1.0)
    alternatives: list[str] = Field(default_factory=list, description="Alternatives")
