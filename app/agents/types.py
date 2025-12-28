"""Type definitions for the multiagent system.

This module defines enums, type aliases, and custom types
used across the agent system.
"""

from enum import Enum
from typing import Literal, TypeAlias


class IntentType(str, Enum):
    """User intent classification types."""

    CATEGORIZE = "categorize"
    ANALYZE = "analyze"
    PLAN = "plan"
    RECOMMEND = "recommend"
    REGISTER = "register"
    QUERY = "query"
    UNKNOWN = "unknown"


class ComplexityType(str, Enum):
    """Query complexity classification."""

    SIMPLE = "simple"
    COMPLEX = "complex"


class PlanStepStatus(str, Enum):
    """Status of a plan step in the Complex Path."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentName(str, Enum):
    """Available agent names for routing."""

    ORCHESTRATOR = "orchestrator"
    CATEGORIZER = "categorizer"
    ANALYST = "analyst"
    PLANNER = "planner"
    RECOMMENDER = "recommender"
    RESPONSE_GENERATOR = "response_generator"
    TASK_PLANNER = "task_planner"
    EXECUTOR = "executor"
    REPLANNER = "replanner"


# Type aliases for clarity
Intent: TypeAlias = Literal[
    "categorize", "analyze", "plan", "recommend", "register", "query", "unknown"
]
Complexity: TypeAlias = Literal["simple", "complex"]
StepStatus: TypeAlias = Literal["pending", "in_progress", "completed", "failed"]

# Agent routing type
AgentRoute: TypeAlias = Literal[
    "orchestrator",
    "categorizer",
    "analyst",
    "planner",
    "recommender",
    "response_generator",
    "task_planner",
    "executor",
    "replanner",
]
