"""LangGraph definition for FinanceGPT hybrid multiagent system."""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.nodes.analyst import analyst_node
from app.agents.nodes.categorizer import categorizer_node
from app.agents.nodes.executor import executor_node
from app.agents.nodes.orchestrator import orchestrator_node
from app.agents.nodes.planner import planner_node
from app.agents.nodes.recommender import recommender_node
from app.agents.nodes.replanner import replanner_node
from app.agents.nodes.response_generator import response_generator_node
from app.agents.nodes.task_planner import task_planner_node
from app.agents.state import AgentState


def route_by_complexity(state: AgentState) -> str:
    """Determine which path to take based on query complexity."""
    return state["query_complexity"]


def route_to_agent(state: AgentState) -> str:
    """Route to the appropriate specialized agent for simple queries."""
    return state["next_agent"]


def should_continue_or_finish(state: AgentState) -> str:
    """Decide whether to continue executing, replan, or finish."""
    # Prevent infinite loops
    if state["iteration_count"] >= state["max_iterations"]:
        return "finish"

    # Check if plan is complete
    current_plan = state.get("current_plan", [])
    all_completed = all(step["status"] == "completed" for step in current_plan)

    if all_completed:
        return "finish"

    # Check if replanning is needed
    if state.get("requires_replan", False):
        return "replan"

    return "continue"


def classify_complexity(state: AgentState) -> AgentState:
    """Classify the query as simple or complex.

    Complex queries require the Plan-Execute-Replan loop.
    Simple queries are handled directly by a single agent.
    """
    messages = state.get("messages", [])
    if not messages:
        return {**state, "query_complexity": "simple"}

    message = messages[-1].content.lower()

    # Indicators of COMPLEX queries
    complex_indicators = [
        # Multiple actions
        " y " in message
        and any(verb in message for verb in ["analiza", "compara", "planifica"]),
        # Extended temporal analysis
        any(
            term in message
            for term in ["trimestre", "semestre", "año", "histórico", "últimos meses"]
        ),
        # Elaborate planning requests
        any(
            term in message
            for term in ["plan de ahorro", "estrategia", "optimizar", "objetivo"]
        ),
        # Multiple comparisons
        "compara" in message and "categorías" in message,
        # Projections
        any(term in message for term in ["proyección", "futuro", "meta", "alcanzar"]),
    ]

    # Indicators of SIMPLE queries
    simple_indicators = [
        # Single actions
        message.startswith("registra") or message.startswith("agrega"),
        # Point-in-time queries
        "cuánto gasté" in message and "hoy" in message,
        # Simple categorizations
        "categoriza" in message and "transacción" in message,
        # Balance queries
        "saldo" in message or "balance" in message,
    ]

    is_complex = any(complex_indicators) and not any(simple_indicators)

    return {
        **state,
        "query_complexity": "complex" if is_complex else "simple",
    }


def create_financegpt_graph() -> StateGraph:
    """Create the hybrid FinanceGPT graph.

    Returns:
        Compiled StateGraph with checkpointing enabled.
    """
    graph = StateGraph(AgentState)

    # Main nodes
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("complexity_classifier", classify_complexity)

    # Simple path nodes
    graph.add_node("categorizer", categorizer_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("planner", planner_node)
    graph.add_node("recommender", recommender_node)

    # Complex path nodes (Plan-Execute-Replan)
    graph.add_node("task_planner", task_planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("replanner", replanner_node)

    # Final node
    graph.add_node("response_generator", response_generator_node)

    # Entry point
    graph.set_entry_point("orchestrator")

    # Edges from orchestrator
    graph.add_edge("orchestrator", "complexity_classifier")

    # Conditional routing based on complexity
    graph.add_conditional_edges(
        "complexity_classifier",
        route_by_complexity,
        {
            "simple": "route_simple",
            "complex": "task_planner",
        },
    )

    # Simple path: direct routing to specialized agent
    graph.add_node("route_simple", lambda state: state)  # Pass-through node
    graph.add_conditional_edges(
        "route_simple",
        route_to_agent,
        {
            "categorizer": "categorizer",
            "analyst": "analyst",
            "planner": "planner",
            "recommender": "recommender",
        },
    )

    # All simple agents go to response generator
    for agent in ["categorizer", "analyst", "planner", "recommender"]:
        graph.add_edge(agent, "response_generator")

    # Complex path: Plan-Execute-Replan loop
    graph.add_edge("task_planner", "executor")
    graph.add_edge("executor", "replanner")

    # Replanner decides whether to continue or finish
    graph.add_conditional_edges(
        "replanner",
        should_continue_or_finish,
        {
            "continue": "executor",
            "replan": "task_planner",
            "finish": "response_generator",
        },
    )

    # Response generator is the final node
    graph.add_edge("response_generator", END)

    return graph.compile(checkpointer=MemorySaver())


# Singleton instance for the application
financegpt_graph = create_financegpt_graph()
