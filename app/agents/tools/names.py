"""Tool-name constants: a leaf module (no imports) so anything can use them.

Toolkits, the false-claim guard and the evals all refer to tools by name; keeping the
names here breaks the import cycle toolkit -> agents.nodes -> action_claims -> toolkit.
"""

from typing import Final

# analysis_tools
ANALYZE_FINANCES_TOOL: Final[str] = "analyze_finances"
SPENDING_TREND_TOOL: Final[str] = "spending_trend"

# budget_tools
CREATE_BUDGET_TOOL: Final[str] = "create_budget"
QUERY_BUDGETS_TOOL: Final[str] = "query_budgets"
UPDATE_BUDGET_TOOL: Final[str] = "update_budget"
DELETE_BUDGET_TOOL: Final[str] = "delete_budget"

# card_tools
CREATE_CARD_TOOL: Final[str] = "create_card"
QUERY_CARDS_TOOL: Final[str] = "query_cards"
PAY_CARD_TOOL: Final[str] = "pay_card"
REMOVE_CARD_PAYMENT_TOOL: Final[str] = "remove_card_payment"
UPDATE_CARD_TOOL: Final[str] = "update_card"
CONFIRM_CARD_CHANGE_TOOL: Final[str] = "confirm_card_change"
DELETE_CARD_TOOL: Final[str] = "delete_card"

# category_tools
MANAGE_CATEGORY_TOOL: Final[str] = "manage_category"

# goal_tools
CREATE_GOAL_TOOL: Final[str] = "create_goal"
QUERY_GOALS_TOOL: Final[str] = "query_goals"
CONTRIBUTE_GOAL_TOOL: Final[str] = "contribute_to_goal"
WITHDRAW_GOAL_TOOL: Final[str] = "withdraw_from_goal"
SET_GOAL_AMOUNT_TOOL: Final[str] = "set_goal_amount"
REMOVE_CONTRIBUTION_TOOL: Final[str] = "remove_goal_contribution"
UPDATE_GOAL_TOOL: Final[str] = "update_goal"
DELETE_GOAL_TOOL: Final[str] = "delete_goal"
PAUSE_GOAL_TOOL: Final[str] = "pause_goal"
RESUME_GOAL_TOOL: Final[str] = "resume_goal"
SET_GOAL_PLAN_TOOL: Final[str] = "set_goal_plan"
CLEAR_GOAL_PLAN_TOOL: Final[str] = "clear_goal_plan"

# movement_tools
FIND_MOVEMENTS_TOOL: Final[str] = "find_movements"

# profile_tools
SET_CURRENCY_TOOL: Final[str] = "set_currency"
SET_TIMEZONE_TOOL: Final[str] = "set_timezone"
UPDATE_PROFILE_TOOL: Final[str] = "update_profile"

# recurring_tools
CREATE_RECURRING_TOOL: Final[str] = "create_recurring"
LIST_RECURRING_TOOL: Final[str] = "list_recurring"
UPDATE_RECURRING_TOOL: Final[str] = "update_recurring"
DELETE_RECURRING_TOOL: Final[str] = "delete_recurring"
PAUSE_RECURRING_TOOL: Final[str] = "pause_recurring"
RESUME_RECURRING_TOOL: Final[str] = "resume_recurring"

# transaction_tools
REGISTER_TRANSACTION_TOOL: Final[str] = "register_transaction"
QUERY_TRANSACTIONS_TOOL: Final[str] = "query_transactions"
ANALYZE_SPENDING_TOOL: Final[str] = "analyze_spending"
UPDATE_TRANSACTION_TOOL: Final[str] = "update_transaction"
DELETE_TRANSACTION_TOOL: Final[str] = "delete_transaction"
# Named 'delete_by_filter' (not 'delete_movements') to avoid colliding with
# manage_category's boolean 'delete_movements' param, which confuses tool routing.
DELETE_BY_FILTER_TOOL: Final[str] = "delete_by_filter"

# card_tools: result prefixes of a schedule change that was only PROPOSED (nothing applied).
PROPOSAL_PREFIX: Final[str] = "PROPUESTA (aún NO aplicada)"
ALREADY_PROPOSED_PREFIX: Final[str] = "Ya está propuesto"
