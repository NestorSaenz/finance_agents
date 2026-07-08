"""Agent nodes for the FinanceGPT graph.

- orchestrator: intent classification and routing
- categorizer: transaction classification using embeddings (RAG)
- tool_agent: ReAct tool-calling agent for all data-driven work
- refusal: declines out-of-scope requests
- response_generator: final response synthesis
"""

from app.agents.nodes.categorizer import categorizer_node
from app.agents.nodes.orchestrator import orchestrator_node
from app.agents.nodes.refusal import refusal_node
from app.agents.nodes.response_generator import response_generator_node
from app.agents.nodes.tool_agent import tool_agent_node

__all__ = [
    "orchestrator_node",
    "categorizer_node",
    "tool_agent_node",
    "refusal_node",
    "response_generator_node",
]
