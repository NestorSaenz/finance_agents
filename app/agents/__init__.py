"""FinanceGPT Multiagent System.

This module contains the LangGraph-based hybrid multiagent system
that powers the conversational financial assistant.

Architecture:
- Simple Path: Direct agent routing for simple queries
- Complex Path: Plan-Execute-Replan for multi-step analysis

Structure:
- constants.py: Static values and configuration
- types.py: Enums and type aliases
- models.py: Pydantic domain models
- interfaces.py: Abstract contracts (ABCs)
- dto.py: API request/response schemas
- dependencies.py: FastAPI dependency injection
- state.py: LangGraph AgentState
- graph.py: LangGraph graph definition
- nodes/: Agent node implementations
- tools/: Agent tools
"""

from app.agents.constants import (
    AGENT_ANALYST,
    AGENT_CATEGORIZER,
    AGENT_EXECUTOR,
    AGENT_ORCHESTRATOR,
    AGENT_PLANNER,
    AGENT_RECOMMENDER,
    AGENT_REPLANNER,
    AGENT_RESPONSE_GENERATOR,
    AGENT_TASK_PLANNER,
    ALL_AGENTS,
    COMPLEX_PATH_AGENTS,
    DEFAULT_MAX_ITERATIONS,
    SIMPLE_PATH_AGENTS,
)
from app.agents.models import (
    AgentResponse,
    AnalysisResult,
    CategorySuggestion,
    ClassificationResult,
    ConversationContext,
    ExecutionResult,
    FinancialContext,
    PlanStep,
    Recommendation,
    SavingsPlan,
)
from app.agents.state import AgentState
from app.agents.types import (
    AgentName,
    AgentRoute,
    Complexity,
    ComplexityType,
    Intent,
    IntentType,
    PlanStepStatus,
    StepStatus,
)

__all__ = [
    # Constants
    "AGENT_ORCHESTRATOR",
    "AGENT_CATEGORIZER",
    "AGENT_ANALYST",
    "AGENT_PLANNER",
    "AGENT_RECOMMENDER",
    "AGENT_RESPONSE_GENERATOR",
    "AGENT_TASK_PLANNER",
    "AGENT_EXECUTOR",
    "AGENT_REPLANNER",
    "ALL_AGENTS",
    "SIMPLE_PATH_AGENTS",
    "COMPLEX_PATH_AGENTS",
    "DEFAULT_MAX_ITERATIONS",
    # Types
    "IntentType",
    "ComplexityType",
    "PlanStepStatus",
    "AgentName",
    "Intent",
    "Complexity",
    "StepStatus",
    "AgentRoute",
    # Models
    "PlanStep",
    "ClassificationResult",
    "ExecutionResult",
    "AgentResponse",
    "ConversationContext",
    "FinancialContext",
    "AnalysisResult",
    "CategorySuggestion",
    "SavingsPlan",
    "Recommendation",
    # State
    "AgentState",
]
