"""Guard against replies that claim a write that no tool performed.

The tool agent is the ONLY path that writes data. If the model says "Registré tus
gastos" in a turn where no write tool was even attempted, the claim is false (it
was invented from the prompt or the conversation) and must never reach the user.

Pure module: no I/O besides logging. A write counts as ATTEMPTED when a mutating
tool ran and did not answer with a "nothing applied" result (a proposal awaiting
confirmation or a dispatch error). Gating on the attempt, rather than on success
markers in the tool text, keeps the guard correct when a tool changes its wording.
"""

import re
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Final

from app.agents.tools.analysis_tools import ANALYZE_FINANCES_TOOL, SPENDING_TREND_TOOL
from app.agents.tools.budget_tools import (
    CREATE_BUDGET_TOOL,
    DELETE_BUDGET_TOOL,
    QUERY_BUDGETS_TOOL,
    UPDATE_BUDGET_TOOL,
)
from app.agents.tools.card_tools import (
    ALREADY_PROPOSED_PREFIX,
    CONFIRM_CARD_CHANGE_TOOL,
    CREATE_CARD_TOOL,
    DELETE_CARD_TOOL,
    PAY_CARD_TOOL,
    PROPOSAL_PREFIX,
    QUERY_CARDS_TOOL,
    REMOVE_CARD_PAYMENT_TOOL,
    UPDATE_CARD_TOOL,
)
from app.agents.tools.category_tools import MANAGE_CATEGORY_TOOL
from app.agents.tools.goal_tools import (
    CONTRIBUTE_GOAL_TOOL,
    CREATE_GOAL_TOOL,
    DELETE_GOAL_TOOL,
    PAUSE_GOAL_TOOL,
    QUERY_GOALS_TOOL,
    REMOVE_CONTRIBUTION_TOOL,
    RESUME_GOAL_TOOL,
    SET_GOAL_AMOUNT_TOOL,
    UPDATE_GOAL_TOOL,
    WITHDRAW_GOAL_TOOL,
)
from app.agents.tools.movement_tools import FIND_MOVEMENTS_TOOL
from app.agents.tools.profile_tools import (
    SET_CURRENCY_TOOL,
    SET_TIMEZONE_TOOL,
    UPDATE_PROFILE_TOOL,
)
from app.agents.tools.recurring_tools import (
    CREATE_RECURRING_TOOL,
    DELETE_RECURRING_TOOL,
    LIST_RECURRING_TOOL,
    PAUSE_RECURRING_TOOL,
    RESUME_RECURRING_TOOL,
    UPDATE_RECURRING_TOOL,
)
from app.agents.tools.transaction_tools import (
    ANALYZE_SPENDING_TOOL,
    DELETE_BY_FILTER_TOOL,
    DELETE_TRANSACTION_TOOL,
    QUERY_TRANSACTIONS_TOOL,
    REGISTER_TRANSACTION_TOOL,
    UPDATE_TRANSACTION_TOOL,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# Prefix of the text a failed dispatch returns (the tool never ran).
DISPATCH_ERROR_PREFIX: Final = "No pude ejecutar la herramienta solicitada"

FALSE_CLAIM_REPLY: Final = (
    "Ojo: en este mensaje todavía no registré ni cambié nada. Si quieres que lo haga, "
    "dime qué registrar (o responde «sí, regístralos» si te propuse algo)."
)

MUTATING_TOOLS: Final[frozenset[str]] = frozenset(
    {
        REGISTER_TRANSACTION_TOOL,
        UPDATE_TRANSACTION_TOOL,
        DELETE_TRANSACTION_TOOL,
        DELETE_BY_FILTER_TOOL,
        CREATE_BUDGET_TOOL,
        UPDATE_BUDGET_TOOL,
        DELETE_BUDGET_TOOL,
        CREATE_GOAL_TOOL,
        UPDATE_GOAL_TOOL,
        DELETE_GOAL_TOOL,
        CONTRIBUTE_GOAL_TOOL,
        WITHDRAW_GOAL_TOOL,
        SET_GOAL_AMOUNT_TOOL,
        REMOVE_CONTRIBUTION_TOOL,
        PAUSE_GOAL_TOOL,
        RESUME_GOAL_TOOL,
        CREATE_CARD_TOOL,
        PAY_CARD_TOOL,
        REMOVE_CARD_PAYMENT_TOOL,
        UPDATE_CARD_TOOL,
        CONFIRM_CARD_CHANGE_TOOL,
        DELETE_CARD_TOOL,
        MANAGE_CATEGORY_TOOL,
        CREATE_RECURRING_TOOL,
        UPDATE_RECURRING_TOOL,
        DELETE_RECURRING_TOOL,
        PAUSE_RECURRING_TOOL,
        RESUME_RECURRING_TOOL,
        SET_CURRENCY_TOOL,
        SET_TIMEZONE_TOOL,
        UPDATE_PROFILE_TOOL,
    }
)

# Every tool that only reads. Together with MUTATING_TOOLS it must cover ALL exposed
# tools (pinned by a test), so a new tool cannot go unclassified.
READ_ONLY_TOOLS: Final[frozenset[str]] = frozenset(
    {
        QUERY_TRANSACTIONS_TOOL,
        ANALYZE_SPENDING_TOOL,
        QUERY_BUDGETS_TOOL,
        QUERY_GOALS_TOOL,
        QUERY_CARDS_TOOL,
        ANALYZE_FINANCES_TOOL,
        SPENDING_TREND_TOOL,
        FIND_MOVEMENTS_TOOL,
        LIST_RECURRING_TOOL,
    }
)

# Tool results that mean "nothing was applied": a proposal awaiting confirmation, a
# dispatch error, a clarifying question ("¿") or a refusal/not-found ("No "). Every
# success string of the toolkits starts with an emoji (checked when this was written).
NOT_APPLIED_PREFIXES: Final[tuple[str, ...]] = (
    PROPOSAL_PREFIX,
    ALREADY_PROPOSED_PREFIX,
    DISPATCH_ERROR_PREFIX,
    "¿",
    "No ",
)

# Only the tail of a text is scanned: a false claim sits at the end of a reply, and the
# cap keeps the clause/negation scan (quadratic in sentence length) bounded.
_MAX_SCAN_CHARS: Final[int] = 8000
_QUOTED_SPAN: Final = re.compile(r'"[^"]*"|“[^”]*”|«[^»]*»|\'[^\']*\'')
# A sentence plus its terminator; a "." between digits ("$199.966") is not a terminator.
_SENTENCE: Final = re.compile(r"((?:[^.!?\n]|\.(?=\d))+)([.!?\n]?)")
_NEGATION: Final = re.compile(r"\b(?:no|ni|nunca|nada|tampoco|ning[uú]n[ao]?)\b", re.IGNORECASE)
# A negation only counts inside the verb's own clause, so "No te preocupes, registré X"
# and "No registré A, pero eliminé B" still flag the second verb.
_CLAUSE_SEPARATOR: Final = re.compile(r"[,;]|\b(?:pero|y|aunque|sino)\b", re.IGNORECASE)
# Template replies such as "✅ Gasto registrado: pizza $50.000" (no first-person verb).
_TEMPLATE_CLAIM: Final = re.compile(
    r"^\W*(?:gastos?|ingresos?|movimientos?|transacci[oó]n(?:es)?)\s+"
    r"(?:registrad|guardad|eliminad|actualizad)\w*",
    re.IGNORECASE,
)
# Money-like figures, most specific alternative first: amounts with a unit ("$2M", "300k",
# "5 millones"), "$"-prefixed amounts, spaced thousands ("1 234 567"), dotted/comma
# thousands ("12.000"), long plain numbers ("50000") and short decimals ("12,5").
_FIGURE: Final = re.compile(
    r"\$?\s?\d+(?:[.,]\d+)?\s?(?:mill[oó]n(?:es)?|mil|k|m)\b"
    r"|\$\s?\d[\d.,]*"
    r"|\d{1,3}(?:\s\d{3})+"
    r"|\d{1,3}(?:[.,]\d{3})+"
    r"|\d{4,}"
    r"|\d+[.,]\d{1,2}\b",
    re.IGNORECASE,
)
_UNIT: Final = re.compile(r"(mill[oó]n(?:es)?|mil|k|m)$", re.IGNORECASE)
_UNIT_MULTIPLIER: Final[dict[str, Decimal]] = {
    "k": Decimal(1_000),
    "mil": Decimal(1_000),
    "m": Decimal(1_000_000),
    "millon": Decimal(1_000_000),
    "millón": Decimal(1_000_000),
    "millones": Decimal(1_000_000),
}
THOUSANDS_GROUP_DIGITS: Final = 3
MIN_PLAIN_FIGURE_DIGITS: Final = 3
YEAR_DIGITS: Final = 4
MIN_YEAR: Final = 1900
MAX_YEAR: Final = 2100
_CLAIM: Final = re.compile(
    r"\b(?:"
    r"registré|anoté|guardé|agregué|añadí|creé|actualicé|modifiqué|cambié|corregí|ajusté"
    r"|eliminé|borré|quité|aboné|aporté|retiré|pausé|reactivé|reanudé|renombré|configuré"
    r"|(?:he|hemos)\s+(?:registrado|guardado|creado|actualizado|eliminado|borrado"
    r"|agregado|anotado)"
    r"|qued(?:ó|aron)\s+(?:registrad|guardad|eliminad|actualizad)\w*"
    r")\b",
    re.IGNORECASE,
)


def _decimal_number(text: str) -> Decimal | None:
    """Parse "12.000", "12,5", "1.234,56", "1,234.56" or "1 234 567" into a Decimal.

    With both separators the LAST one is the decimal point (Colombian "1.234,56" and
    US "1,234.56" both work). A single kind repeated is a thousands separator; a lone
    separator followed by exactly 3 digits is thousands ("12.000"), otherwise decimal
    ("12,5", "1.5").
    """
    compact = text.replace(" ", "")
    dots, commas = compact.count("."), compact.count(",")
    if dots and commas:
        decimal_sep = "." if compact.rfind(".") > compact.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        compact = compact.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif dots + commas > 1:
        compact = compact.replace(".", "").replace(",", "")
    elif dots + commas == 1:
        sep = "." if dots else ","
        _, _, tail = compact.partition(sep)
        compact = compact.replace(sep, "" if len(tail) == THOUSANDS_GROUP_DIGITS else ".")
    try:
        return Decimal(compact)
    except InvalidOperation:
        return None


def _figure_value(raw: str) -> Decimal | None:
    """Numeric value of a matched figure, or None when it is not a money-like figure."""
    token = raw.strip().lstrip("$").strip()
    unit = _UNIT.search(token)
    number = _decimal_number(token[: unit.start()] if unit else token)
    if number is None:
        return None
    is_plain_integer = unit is None and not raw.strip().startswith("$") and token.isdigit()
    if is_plain_integer and len(token) < MIN_PLAIN_FIGURE_DIGITS:
        return None  # day / month numbers
    if is_plain_integer and len(token) == YEAR_DIGITS and MIN_YEAR <= number <= MAX_YEAR:
        return None  # years
    if unit is None:
        return number
    return number * _UNIT_MULTIPLIER[unit.group(1).lower().removesuffix("es")]


def _figures(text: str) -> frozenset[Decimal]:
    """Money-like figures in ``text`` as Decimals, so "$2M" equals "2.000.000"."""
    values = (_figure_value(match) for match in _FIGURE.findall(text[-_MAX_SCAN_CHARS:]))
    return frozenset(value for value in values if value is not None)


def invented_figures(reply: str, history_text: str) -> bool:
    """True when ``reply`` quotes a figure that the conversation never mentioned.

    Heuristic: a recount of past writes ("sí, registré tu Uber de $12.000") repeats
    figures already said in the conversation, while an invented success quotes NEW
    ones (the production bug invented "$199.966" out of thin air).
    """
    return not _figures(reply) <= _figures(history_text)


def is_write_attempt(tool_name: str, result: str) -> bool:
    """True when a mutating tool ran and its result does not say "nothing applied"."""
    return tool_name in MUTATING_TOOLS and not result.startswith(NOT_APPLIED_PREFIXES)


def is_write_refused(tool_name: str, result: str) -> bool:
    """True when a mutating tool ran but reported that nothing was applied."""
    return tool_name in MUTATING_TOOLS and result.startswith(NOT_APPLIED_PREFIXES)


def _is_question(sentence: str, terminator: str) -> bool:
    return terminator == "?" or sentence.lstrip().startswith("¿")


def _is_negated(sentence: str, verb_start: int) -> bool:
    """True when a negation precedes the verb inside the verb's own clause."""
    clause = _CLAUSE_SEPARATOR.split(sentence[:verb_start])[-1]
    return _NEGATION.search(clause) is not None


def _sentence_claims_write(sentence: str, terminator: str) -> bool:
    """A completed-write statement that is not a question and not negated."""
    if _is_question(sentence, terminator):
        return False
    if _TEMPLATE_CLAIM.search(sentence) is not None:
        return True
    return any(not _is_negated(sentence, match.start()) for match in _CLAIM.finditer(sentence))


def claims_completed_write(text: str) -> bool:
    """True when ``text`` affirms, in the first person, that something was written."""
    unquoted = _QUOTED_SPAN.sub(" ", text[-_MAX_SCAN_CHARS:])
    return any(
        _sentence_claims_write(match.group(1), match.group(2))
        for match in _SENTENCE.finditer(unquoted)
    )


def enforce_truthful_reply(
    text: str,
    *,
    write_attempted: bool,
    write_refused: bool = False,
    tools_called: Sequence[str] = (),
    history_text: str = "",
    history_claims_text: str = "",
) -> str:
    """Replace a write claim that shows evidence of being false.

    Replaced: a write tool ran but applied nothing (proposal, not found, question,
    dispatch error) and none applied; or no tool ran and there is no conversation
    showing a completed write whose figures the reply repeats (the production bug: a
    bare "sí" in a new chat). Kept and logged: read-only tools ran (e.g. "¿registraste
    el Uber?" -> find_movements -> "Sí, registré tu Uber"), or a zero-tool recount that
    the history itself backs. ``history_text`` is the whole conversation (a recount may
    repeat figures the user said); ``history_claims_text`` is ONLY the assistant's earlier
    turns, the sole valid evidence that a write was completed (a user typing "registré 50"
    proves nothing).
    """
    if write_attempted or not claims_completed_write(text):
        return text
    if write_refused:
        return _block(text)
    if tools_called:
        logger.warning("Possible false write claim", reply=text[:200], tools=list(tools_called))
        return text
    backed_by_history = claims_completed_write(history_claims_text)
    if backed_by_history and not invented_figures(text, history_text):
        logger.warning("Possible false write claim", reply=text[:200], reason="recount_from_history")
        return text
    return _block(text)


def _block(text: str) -> str:
    logger.warning("Blocked false write claim", reply=text[:200])
    return FALSE_CLAIM_REPLY
