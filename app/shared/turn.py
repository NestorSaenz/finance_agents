"""Request-scoped identity of the current chat turn.

Some actions must span TWO user turns (propose now, apply after the user's later
"sí"). The code that enforces that needs to know which turn it is running in and
which conversation it belongs to, without threading them through ``dispatch``
(which keeps its ``(name, args, user_id)`` security contract intact). Same pattern
as :mod:`app.shared.clock`: the tool agent binds the turn to a ``ContextVar`` and
tools read it via :func:`current_turn`.

Outside a bound turn ``current_turn()`` is ``None`` and callers must FAIL CLOSED.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TurnContext:
    """Identifies one chat request (``turn_id``) inside a conversation."""

    turn_id: str
    conversation_id: str


_CURRENT_TURN: ContextVar[TurnContext | None] = ContextVar("current_turn", default=None)


@contextmanager
def bound_turn(turn: TurnContext) -> Iterator[None]:
    """Bind ``turn`` as the current turn for the duration of the block.

    The previous value is restored on exit (reentrant/nesting-safe via the token).
    """
    token = _CURRENT_TURN.set(turn)
    try:
        yield
    finally:
        _CURRENT_TURN.reset(token)


def current_turn() -> TurnContext | None:
    """Return the bound turn, or ``None`` when no turn is bound."""
    return _CURRENT_TURN.get()
