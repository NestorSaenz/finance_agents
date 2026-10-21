"""Single place that wires every toolkit into the composite the agent sees.

Production (``graph.py``) and the tests that pin tool classification both build the
toolkit through ``build_composite_toolkit``, so a toolkit wired here can never escape
the "every tool is mutating or read-only" check.
"""

from dataclasses import dataclass

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
from app.src.analysis.interfaces import AnalysisServiceABC, MovementFinderServiceABC
from app.src.budgets.interfaces import BudgetServiceABC
from app.src.cards.interfaces import CardScheduleChangeServiceABC, CreditCardServiceABC
from app.src.goals.interfaces import GoalServiceABC
from app.src.recurring.interfaces import RecurringServiceABC
from app.src.transactions.interfaces import TransactionServiceABC
from app.src.users.interfaces import UserProfileServiceABC


@dataclass(frozen=True)
class ToolServices:
    """The application services the toolkits wrap."""

    transactions: TransactionServiceABC
    budgets: BudgetServiceABC
    goals: GoalServiceABC
    cards: CreditCardServiceABC
    card_schedule: CardScheduleChangeServiceABC
    analysis: AnalysisServiceABC
    recurring: RecurringServiceABC
    profile: UserProfileServiceABC
    movements: MovementFinderServiceABC


def build_composite_toolkit(services: ToolServices) -> CompositeToolkit:
    """Every toolkit the agent can call, in the order the model sees their schemas."""
    return CompositeToolkit(
        [
            TransactionToolkit(services.transactions, cards=services.cards, budgets=services.budgets),
            BudgetToolkit(services.budgets),
            GoalToolkit(services.goals),
            CardToolkit(services.cards, services.card_schedule),
            AnalysisToolkit(services.analysis),
            CategoryToolkit(services.transactions, services.budgets),
            RecurringToolkit(services.recurring, cards=services.cards),
            ProfileToolkit(services.profile),
            MovementToolkit(services.movements),
        ]
    )
