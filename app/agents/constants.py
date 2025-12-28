"""Constants for the multiagent system.

This module defines static values used across all agents.
"""

# Agent names
AGENT_ORCHESTRATOR = "orchestrator"
AGENT_CATEGORIZER = "categorizer"
AGENT_ANALYST = "analyst"
AGENT_PLANNER = "planner"
AGENT_RECOMMENDER = "recommender"
AGENT_RESPONSE_GENERATOR = "response_generator"
AGENT_TASK_PLANNER = "task_planner"
AGENT_EXECUTOR = "executor"
AGENT_REPLANNER = "replanner"

# All available agents
ALL_AGENTS = [
    AGENT_ORCHESTRATOR,
    AGENT_CATEGORIZER,
    AGENT_ANALYST,
    AGENT_PLANNER,
    AGENT_RECOMMENDER,
    AGENT_RESPONSE_GENERATOR,
    AGENT_TASK_PLANNER,
    AGENT_EXECUTOR,
    AGENT_REPLANNER,
]

# Simple path agents (direct execution)
SIMPLE_PATH_AGENTS = [
    AGENT_CATEGORIZER,
    AGENT_ANALYST,
    AGENT_PLANNER,
    AGENT_RECOMMENDER,
]

# Complex path agents (Plan-Execute-Replan)
COMPLEX_PATH_AGENTS = [
    AGENT_TASK_PLANNER,
    AGENT_EXECUTOR,
    AGENT_REPLANNER,
]

# Iteration limits
DEFAULT_MAX_ITERATIONS = 10
MAX_PLAN_STEPS = 7

# Classification thresholds
COMPLEXITY_CONFIDENCE_THRESHOLD = 0.7

# LLM Configuration for agents
CLASSIFIER_TEMPERATURE = 0.1
CLASSIFIER_MAX_TOKENS = 50
AGENT_TEMPERATURE = 0.7
AGENT_MAX_TOKENS = 1024
