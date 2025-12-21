"""Executor agent node (Complex Path).

The executor runs each step of the plan by delegating
to the appropriate specialized agent and collecting results.
"""

from app.agents.state import AgentState, PlanStep
from app.core.logging import get_logger

logger = get_logger(__name__)

# Agent node functions registry
# These will be populated when the actual agent implementations are ready
AGENT_REGISTRY: dict = {}


async def executor_node(state: AgentState) -> AgentState:
    """Execute the current step in the plan.

    Args:
        state: Current agent state with plan.

    Returns:
        Updated state with step results.
    """
    current_plan = state.get("current_plan", [])
    current_step_index = state.get("current_step_index", 0)
    execution_history = state.get("execution_history", [])
    iteration_count = state.get("iteration_count", 0)

    if current_step_index >= len(current_plan):
        logger.info("No more steps to execute")
        return {
            **state,
            "should_respond": True,
        }

    current_step = current_plan[current_step_index]
    logger.info(
        "Executing step",
        step_number=current_step["step_number"],
        description=current_step["description"],
        agent=current_step["assigned_agent"],
    )

    # Mark step as in progress
    current_step["status"] = "in_progress"

    try:
        # Execute the step
        result = await _execute_step(current_step, state)

        # Mark step as completed
        current_step["status"] = "completed"
        current_step["result"] = result

        # Add to execution history
        execution_history.append(
            {
                "step_number": current_step["step_number"],
                "description": current_step["description"],
                "agent": current_step["assigned_agent"],
                "result": result,
                "success": True,
            }
        )

        logger.info(
            "Step completed successfully",
            step_number=current_step["step_number"],
        )

    except Exception as e:
        # Mark step as failed
        current_step["status"] = "failed"
        current_step["error"] = str(e)

        # Add to execution history
        execution_history.append(
            {
                "step_number": current_step["step_number"],
                "description": current_step["description"],
                "agent": current_step["assigned_agent"],
                "error": str(e),
                "success": False,
            }
        )

        logger.error(
            "Step failed",
            step_number=current_step["step_number"],
            error=str(e),
        )

    # Update plan in state
    updated_plan = current_plan.copy()
    updated_plan[current_step_index] = current_step

    return {
        **state,
        "current_plan": updated_plan,
        "current_step_index": current_step_index + 1,
        "execution_history": execution_history,
        "iteration_count": iteration_count + 1,
    }


async def _execute_step(step: PlanStep, state: AgentState) -> dict:
    """Execute a single step by delegating to the appropriate agent.

    Args:
        step: The step to execute.
        state: Current agent state.

    Returns:
        Result from the agent execution.

    TODO: Replace with actual agent delegation.
    """
    agent_name = step["assigned_agent"]
    description = step["description"]

    # Placeholder implementation
    # In the real implementation, this would:
    # 1. Look up the agent in the registry
    # 2. Execute the agent with appropriate parameters
    # 3. Return the agent's results

    logger.info(
        "Delegating to agent",
        agent=agent_name,
        description=description,
    )

    # Simulate agent execution
    result = {
        "agent": agent_name,
        "description": description,
        "data": {},
        "success": True,
    }

    return result
