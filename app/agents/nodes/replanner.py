"""Replanner agent node (Complex Path).

The replanner evaluates execution results and decides whether to:
- Continue with the next step
- Adjust the plan based on results
- Finish if the plan is complete
"""

from app.agents.state import AgentState
from app.core.logging import get_logger

logger = get_logger(__name__)


async def replanner_node(state: AgentState) -> AgentState:
    """Evaluate execution results and decide next action.

    Args:
        state: Current agent state with execution history.

    Returns:
        Updated state with replan decision.
    """
    current_plan = state.get("current_plan", [])
    execution_history = state.get("execution_history", [])
    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 10)

    logger.info(
        "Replanner evaluating",
        executed_steps=len(execution_history),
        total_steps=len(current_plan),
        iteration=iteration_count,
    )

    # Check for completion
    completed_count = sum(1 for step in current_plan if step["status"] == "completed")
    failed_count = sum(1 for step in current_plan if step["status"] == "failed")
    pending_count = sum(1 for step in current_plan if step["status"] == "pending")

    logger.info(
        "Plan status",
        completed=completed_count,
        failed=failed_count,
        pending=pending_count,
    )

    # Determine if replanning is needed
    requires_replan = False

    # Check if too many failures occurred
    if failed_count >= 2:
        logger.warning("Multiple failures detected, may need to replan")
        # TODO: Implement smarter replanning logic
        # For now, we'll try to continue

    # Check if we need to adjust based on results
    if execution_history:
        last_result = execution_history[-1]
        if not last_result.get("success", True):
            # Last step failed, might need to replan
            if failed_count >= 2:
                requires_replan = True
                logger.info("Triggering replan due to failures")

    # Check for max iterations
    if iteration_count >= max_iterations:
        logger.warning("Max iterations reached, forcing completion")
        # Mark remaining steps as skipped
        for step in current_plan:
            if step["status"] == "pending":
                step["status"] = "completed"
                step["result"] = {"skipped": True, "reason": "max_iterations"}

    return {
        **state,
        "requires_replan": requires_replan,
        "should_respond": pending_count == 0 and not requires_replan,
    }
