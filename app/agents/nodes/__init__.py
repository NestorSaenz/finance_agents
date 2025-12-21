"""Agent nodes for the LangGraph multiagent system.

Each node represents a specialized agent with specific responsibilities:

Base Agents (both paths):
- orchestrator: Intent classification and routing
- categorizer: Transaction classification using embeddings
- analyst: Spending pattern detection and metrics
- planner: Savings plans and financial strategies
- recommender: Proactive alerts and optimization suggestions
- response_generator: Final response synthesis

Complex Path Agents:
- task_planner: Decomposes complex queries into executable steps
- executor: Executes plan steps by delegating to appropriate agents
- replanner: Evaluates results and adjusts plan as needed
"""

from app.agents.nodes.analyst import analyst_node
from app.agents.nodes.categorizer import categorizer_node
from app.agents.nodes.executor import executor_node
from app.agents.nodes.orchestrator import orchestrator_node
from app.agents.nodes.planner import planner_node
from app.agents.nodes.recommender import recommender_node
from app.agents.nodes.replanner import replanner_node
from app.agents.nodes.response_generator import response_generator_node
from app.agents.nodes.task_planner import task_planner_node

__all__ = [
    "orchestrator_node",
    "categorizer_node",
    "analyst_node",
    "planner_node",
    "recommender_node",
    "response_generator_node",
    "task_planner_node",
    "executor_node",
    "replanner_node",
]
