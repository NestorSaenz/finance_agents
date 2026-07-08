"""Type definitions for the multiagent system."""

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
    OFF_TOPIC = "off_topic"  # Not about the user's personal finances -> declined
    UNKNOWN = "unknown"


class AgentName(str, Enum):
    """Routing targets reachable from the orchestrator."""

    ORCHESTRATOR = "orchestrator"
    CATEGORIZER = "categorizer"
    TOOL_AGENT = "tool_agent"
    RESPONSE_GENERATOR = "response_generator"
    REFUSAL = "refusal"


# Type aliases for clarity
Intent: TypeAlias = Literal[
    "categorize", "analyze", "plan", "recommend", "register", "query", "off_topic", "unknown"
]

AgentRoute: TypeAlias = Literal[
    "orchestrator",
    "categorizer",
    "tool_agent",
    "response_generator",
    "refusal",
]
