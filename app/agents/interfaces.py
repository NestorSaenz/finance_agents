"""Interfaces (ABCs) for the multiagent system.

This module defines abstract contracts that agent implementations
must follow, enabling dependency inversion and testability.
"""

from abc import ABC, abstractmethod
from typing import Any

from app.agents.models import (
    AnalysisResult,
    CategorySuggestion,
    ClassificationResult,
    PlanStep,
    Recommendation,
    SavingsPlan,
)
from app.agents.state import AgentState
from app.shared.interfaces.llm import LLMInterface


class ClassifierInterface(ABC):
    """Contract for query classification."""

    @abstractmethod
    async def classify(
        self,
        message: str,
        llm: LLMInterface,
    ) -> ClassificationResult:
        """Classify a user message for intent and complexity.

        Args:
            message: The user's message to classify.
            llm: LLM client for classification.

        Returns:
            ClassificationResult with intent, complexity, and next agent.
        """
        pass


class AgentNodeInterface(ABC):
    """Base contract for all agent nodes."""

    @abstractmethod
    async def process(self, state: AgentState) -> AgentState:
        """Process the current state and return updated state.

        Args:
            state: Current agent state.

        Returns:
            Updated agent state.
        """
        pass


class CategorizerInterface(ABC):
    """Contract for transaction categorization."""

    @abstractmethod
    async def categorize(
        self,
        description: str,
        amount: float | None = None,
    ) -> CategorySuggestion:
        """Categorize a transaction based on description.

        Args:
            description: Transaction description.
            amount: Optional transaction amount for context.

        Returns:
            CategorySuggestion with category and confidence.
        """
        pass


class AnalystInterface(ABC):
    """Contract for financial analysis."""

    @abstractmethod
    async def analyze_spending(
        self,
        user_id: str,
        period_days: int = 30,
    ) -> AnalysisResult:
        """Analyze user spending patterns.

        Args:
            user_id: User identifier.
            period_days: Number of days to analyze.

        Returns:
            AnalysisResult with totals, by-category breakdown, and insights.
        """
        pass


class PlannerInterface(ABC):
    """Contract for financial planning."""

    @abstractmethod
    async def create_savings_plan(
        self,
        user_id: str,
        goal_name: str,
        target_amount: float,
        deadline_months: int | None = None,
    ) -> SavingsPlan:
        """Create a savings plan for a goal.

        Args:
            user_id: User identifier.
            goal_name: Name of the savings goal.
            target_amount: Target amount to save.
            deadline_months: Optional deadline in months.

        Returns:
            SavingsPlan with monthly contribution and recommendations.
        """
        pass


class RecommenderInterface(ABC):
    """Contract for generating recommendations."""

    @abstractmethod
    async def generate_recommendations(
        self,
        user_id: str,
        context: dict[str, Any] | None = None,
    ) -> list[Recommendation]:
        """Generate personalized financial recommendations.

        Args:
            user_id: User identifier.
            context: Optional context (recent analysis, goals, etc.).

        Returns:
            List of prioritized recommendations.
        """
        pass


class TaskPlannerInterface(ABC):
    """Contract for complex query planning."""

    @abstractmethod
    async def create_plan(
        self,
        query: str,
        context: dict[str, Any] | None = None,
    ) -> list[PlanStep]:
        """Create an execution plan for a complex query.

        Args:
            query: The complex user query.
            context: Optional context for planning.

        Returns:
            List of PlanStep objects defining the execution plan.
        """
        pass


class ExecutorInterface(ABC):
    """Contract for plan step execution."""

    @abstractmethod
    async def execute_step(
        self,
        step: PlanStep,
        state: AgentState,
    ) -> AgentState:
        """Execute a single plan step.

        Args:
            step: The plan step to execute.
            state: Current agent state.

        Returns:
            Updated agent state with step results.
        """
        pass


class ReplannerInterface(ABC):
    """Contract for plan evaluation and adjustment."""

    @abstractmethod
    async def evaluate_and_replan(
        self,
        state: AgentState,
    ) -> tuple[AgentState, bool]:
        """Evaluate execution and decide whether to continue, replan, or finish.

        Args:
            state: Current agent state with execution history.

        Returns:
            Tuple of (updated state, needs_replan flag).
        """
        pass


class ResponseGeneratorInterface(ABC):
    """Contract for final response generation."""

    @abstractmethod
    async def generate_response(
        self,
        state: AgentState,
    ) -> str:
        """Generate the final user-facing response.

        Args:
            state: Final agent state with all results.

        Returns:
            Formatted response string for the user.
        """
        pass
