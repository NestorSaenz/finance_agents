"""Task planner agent node (Complex Path).

The task planner decomposes complex user queries into
a sequence of executable steps, assigning each step
to the appropriate specialized agent.
"""

from app.agents.state import AgentState, PlanStep
from app.core.logging import get_logger

logger = get_logger(__name__)


async def task_planner_node(state: AgentState) -> AgentState:
    """Create an execution plan for complex queries.

    Args:
        state: Current agent state with user query.

    Returns:
        Updated state with execution plan.
    """
    messages = state.get("messages", [])
    detected_intent = state.get("detected_intent", "unknown")
    requires_replan = state.get("requires_replan", False)

    logger.info(
        "Task planner processing",
        intent=detected_intent,
        is_replan=requires_replan,
    )

    if requires_replan:
        # Adjust existing plan based on execution history
        current_plan = state.get("current_plan", [])
        execution_history = state.get("execution_history", [])
        plan = _adjust_plan(current_plan, execution_history)
        logger.info("Plan adjusted", step_count=len(plan))
    else:
        # Create new plan from scratch
        user_message = messages[-1].content if messages else ""
        plan = _create_plan(user_message, detected_intent)
        logger.info("New plan created", step_count=len(plan))

    return {
        **state,
        "current_plan": plan,
        "current_step_index": 0,
        "requires_replan": False,
        "execution_history": state.get("execution_history", []),
    }


def _create_plan(user_message: str, intent: str) -> list[PlanStep]:
    """Create an execution plan based on user message and intent.

    Args:
        user_message: The user's original message.
        intent: Detected intent.

    Returns:
        List of plan steps.

    TODO: Replace with LLM-based plan generation.
    """
    message_lower = user_message.lower()

    # Default plan template for complex analysis
    plan: list[PlanStep] = []

    # Step 1: Data retrieval
    plan.append(
        PlanStep(
            step_number=1,
            description="Recuperar datos financieros del usuario",
            assigned_agent="analyst",
            status="pending",
            result=None,
            error=None,
        )
    )

    # Step 2: Analysis (if needed)
    if any(term in message_lower for term in ["analiza", "patrones", "gastos"]):
        plan.append(
            PlanStep(
                step_number=2,
                description="Analizar patrones de gasto",
                assigned_agent="analyst",
                status="pending",
                result=None,
                error=None,
            )
        )

    # Step 3: Planning (if needed)
    if any(term in message_lower for term in ["plan", "ahorro", "estrategia", "meta"]):
        plan.append(
            PlanStep(
                step_number=len(plan) + 1,
                description="Crear plan de ahorro personalizado",
                assigned_agent="planner",
                status="pending",
                result=None,
                error=None,
            )
        )

    # Step 4: Recommendations
    plan.append(
        PlanStep(
            step_number=len(plan) + 1,
            description="Generar recomendaciones finales",
            assigned_agent="recommender",
            status="pending",
            result=None,
            error=None,
        )
    )

    return plan


def _adjust_plan(
    current_plan: list[PlanStep],
    execution_history: list[dict],
) -> list[PlanStep]:
    """Adjust the plan based on execution results.

    Args:
        current_plan: The current execution plan.
        execution_history: History of executed steps.

    Returns:
        Adjusted plan.

    TODO: Replace with LLM-based plan adjustment.
    """
    adjusted_plan = []

    for step in current_plan:
        if step["status"] == "failed":
            # Retry failed steps with modifications
            adjusted_step = PlanStep(
                step_number=step["step_number"],
                description=f"[Retry] {step['description']}",
                assigned_agent=step["assigned_agent"],
                status="pending",
                result=None,
                error=None,
            )
            adjusted_plan.append(adjusted_step)
        elif step["status"] == "pending":
            adjusted_plan.append(step)

    return adjusted_plan
