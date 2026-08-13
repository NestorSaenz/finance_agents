"""LangGraph definition for the FinanceGPT hybrid multiagent system.

The graph is built by :func:`create_financegpt_graph`, which receives the
collaborators (LLMs, embedding client, vector store) and binds them to each
node via :func:`functools.partial`. This is required because LangGraph only
passes the ``state`` argument to a node, so any extra dependency must be bound
ahead of time. Building through a factory also keeps the graph testable: tests
inject mocked clients instead of reaching real providers.
"""

from collections.abc import Hashable
from functools import lru_cache, partial
from typing import TYPE_CHECKING

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.nodes.categorizer import categorizer_node
from app.agents.nodes.orchestrator import orchestrator_node
from app.agents.nodes.refusal import refusal_node
from app.agents.nodes.response_generator import response_generator_node
from app.agents.nodes.tool_agent import CategoriesProvider, tool_agent_node
from app.agents.state import AgentState
from app.agents.tools.base import Toolkit
from app.agents.types import AgentName
from app.shared.interfaces.embedding import EmbeddingInterface
from app.shared.interfaces.llm import LLMInterface
from app.shared.interfaces.vector_store import VectorStoreInterface

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


# Targets reachable directly from the orchestrator, by the classified intent.
# Data-driven intents route to the tool-calling agent (its own tool loop absorbs
# what the old dedicated + Plan-Execute-Replan nodes used to do).
SIMPLE_PATH_TARGETS: dict[Hashable, str] = {
    AgentName.CATEGORIZER.value: "categorizer",
    AgentName.TOOL_AGENT.value: "tool_agent",
    AgentName.RESPONSE_GENERATOR.value: "response_generator",
    AgentName.REFUSAL.value: "refusal",
}


def route_to_agent(state: AgentState) -> str:
    """Return the node chosen by the orchestrator for the current intent.

    Falls back to the response generator when the requested target is not valid
    (e.g. an unknown intent), avoiding dead-end routing.
    """
    next_agent = state.get("next_agent", AgentName.RESPONSE_GENERATOR.value)
    if next_agent not in SIMPLE_PATH_TARGETS:
        return AgentName.RESPONSE_GENERATOR.value
    return next_agent


def create_financegpt_graph(
    llm_simple: LLMInterface,
    llm_complex: LLMInterface,
    embedding_client: EmbeddingInterface,
    vector_store: VectorStoreInterface,
    toolkit: Toolkit,
    categories_provider: "CategoriesProvider | None" = None,
) -> "CompiledStateGraph":
    """Create and compile the FinanceGPT graph.

    Flow: the orchestrator classifies intent, then routes to exactly one target:
    ``categorizer`` (RAG classify a described concept), ``tool_agent`` (all
    data-driven work, via its own tool loop), ``refusal`` (off-topic), or the
    ``response_generator`` (greetings / general). Each target is terminal.

    Args:
        llm_simple: Fast LLM used for classification and categorization.
        llm_complex: More capable LLM used for the tool agent and responses.
        embedding_client: Client used by the categorizer for semantic search.
        vector_store: Vector store queried during categorization.
        toolkit: Toolkit (transactions + budgets + goals) for the tool agent.

    Returns:
        Compiled StateGraph with in-memory checkpointing enabled.
    """
    graph = StateGraph(AgentState)

    # Entry node. Dependencies are bound so LangGraph only passes state.
    graph.add_node("orchestrator", partial(orchestrator_node, llm=llm_simple))

    graph.add_node(
        "categorizer",
        partial(
            categorizer_node,
            embedding_client=embedding_client,
            vector_store=vector_store,
            llm=llm_simple,
        ),
    )
    graph.add_node(
        "tool_agent",
        partial(
            tool_agent_node,
            llm=llm_complex,
            toolkit=toolkit,
            categories_provider=categories_provider,
        ),
    )
    graph.add_node("response_generator", partial(response_generator_node, llm=llm_complex))
    graph.add_node("refusal", refusal_node)

    graph.set_entry_point("orchestrator")

    # Route to a single target based on the classified intent.
    graph.add_conditional_edges("orchestrator", route_to_agent, SIMPLE_PATH_TARGETS)

    # The categorizer hands off to the response generator to phrase the reply.
    graph.add_edge("categorizer", "response_generator")

    # The tool agent and the refusal node produce their own final answer and end.
    graph.add_edge("tool_agent", END)
    graph.add_edge("refusal", END)
    graph.add_edge("response_generator", END)

    return graph.compile(checkpointer=MemorySaver())


@lru_cache
def get_compiled_graph() -> "CompiledStateGraph":
    """Build the production graph once, wiring the real providers.

    Imported lazily so that constructing the clients (which need API keys) is
    deferred to the first chat request instead of happening at import time.
    """
    from app.agents.tools.analysis_tools import AnalysisToolkit
    from app.agents.tools.budget_tools import BudgetToolkit
    from app.agents.tools.card_tools import CardToolkit
    from app.agents.tools.category_tools import CategoryToolkit
    from app.agents.tools.composite_toolkit import CompositeToolkit
    from app.agents.tools.goal_tools import GoalToolkit
    from app.agents.tools.movement_tools import MovementToolkit
    from app.agents.tools.profile_tools import ProfileToolkit
    from app.agents.tools.recurring_tools import RecurringToolkit
    from app.agents.tools.transaction_tools import TransactionToolkit
    from app.shared.dependencies import (
        get_database,
        get_embedding_client,
        get_llm_complex,
        get_llm_simple,
        get_vector_store,
    )
    from app.src.analysis.services.analysis_service import AnalysisService
    from app.src.analysis.services.movement_finder import MovementFinder
    from app.src.budgets.repositories.budget_repository import BudgetRepository
    from app.src.budgets.services.budget_service import BudgetService
    from app.src.budgets.services.spending_provider import TransactionSpendingProvider
    from app.src.cards.repositories.card_payment_repository import CardPaymentRepository
    from app.src.cards.repositories.credit_card_repository import CreditCardRepository
    from app.src.cards.services.credit_card_service import CreditCardService
    from app.src.cards.services.spending_provider import TransactionCardSpendingProvider
    from app.src.goals.repositories.goal_contribution_repository import (
        GoalContributionRepository,
    )
    from app.src.goals.repositories.goal_repository import GoalRepository
    from app.src.goals.services.goal_service import GoalService
    from app.src.recurring.repositories.recurring_repository import RecurringRepository
    from app.src.recurring.services.recurring_service import RecurringService
    from app.src.transactions.repositories.transaction_repository import TransactionRepository
    from app.src.transactions.services.semantic_categorizer import SemanticTransactionCategorizer
    from app.src.transactions.services.transaction_service import TransactionService
    from app.src.users.repositories.user_profile_repository import UserProfileRepository
    from app.src.users.services.user_profile_service import UserProfileService

    embedding_client = get_embedding_client()
    vector_store = get_vector_store()
    db = get_database()

    transaction_service = TransactionService(
        TransactionRepository(db),
        SemanticTransactionCategorizer(embedding_client, vector_store),
    )
    budget_service = BudgetService(BudgetRepository(db), TransactionSpendingProvider(db))
    goal_service = GoalService(GoalRepository(db), GoalContributionRepository(db))
    card_service = CreditCardService(
        CreditCardRepository(db),
        CardPaymentRepository(db),
        TransactionCardSpendingProvider(db),
    )
    user_profile_service = UserProfileService(UserProfileRepository(db))
    analysis_service = AnalysisService(
        transaction_service,
        budget_service,
        goal_service,
        card_service,
        user_profile_service,
    )
    recurring_service = RecurringService(
        RecurringRepository(db), transaction_service, card_service, user_profile_service
    )
    movement_finder = MovementFinder(transaction_service, card_service, goal_service)
    toolkit = CompositeToolkit(
        [
            TransactionToolkit(transaction_service, cards=card_service, budgets=budget_service),
            BudgetToolkit(budget_service),
            GoalToolkit(goal_service),
            CardToolkit(card_service),
            AnalysisToolkit(analysis_service),
            CategoryToolkit(transaction_service, budget_service),
            RecurringToolkit(recurring_service, cards=card_service),
            ProfileToolkit(user_profile_service),
            MovementToolkit(movement_finder),
        ]
    )

    return create_financegpt_graph(
        llm_simple=get_llm_simple(),
        llm_complex=get_llm_complex(),
        embedding_client=embedding_client,
        vector_store=vector_store,
        toolkit=toolkit,
        categories_provider=transaction_service.list_categories,
    )
