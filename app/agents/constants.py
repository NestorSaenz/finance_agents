"""Constants for the multiagent system."""

# Kept on the state for backward compatibility; the single tool-calling agent
# bounds its own work via MAX_TOOL_ROUNDS, so this no longer drives a loop.
DEFAULT_MAX_ITERATIONS = 5

# Hard backstop for the whole graph: LangGraph raises GraphRecursionError past
# this many node steps.
GRAPH_RECURSION_LIMIT = 15

# Wall-clock ceiling for a single chat turn (seconds); a hung provider call or
# runaway loop is aborted and degraded to a fallback response.
GRAPH_TIMEOUT_SECONDS = 60.0

# LLM configuration for the classifier.
CLASSIFIER_TEMPERATURE = 0.1
CLASSIFIER_MAX_TOKENS = 50
