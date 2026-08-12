"""Request-scoped 'today' resolved in the user's local timezone.

Relative dates the user speaks ("hoy", "ayer") must resolve on their LOCAL
calendar day, not UTC — near midnight a Bogota user's "hoy" is still yesterday in
UTC. The chat node computes the local ``today`` ONCE per turn (from the user's
stored IANA timezone) and binds it to a ``ContextVar`` so every tool dispatched in
that turn reads the same day, without threading the value through ``dispatch``
(which keeps its ``(name, args, user_id)`` security contract intact).

Outside a bound turn (background jobs, tests) ``current_today()`` falls back to
UTC, so importing this never depends on a request being in flight.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.logging import get_logger

logger = get_logger(__name__)

# The user's local "today" for the current chat turn. ``None`` when no turn is
# bound, so readers fall back to UTC (see ``current_today``).
_LOCAL_TODAY: ContextVar[date | None] = ContextVar("local_today", default=None)


def local_today(tz: str | None) -> date:
    """Return the current calendar day in IANA timezone ``tz``.

    Falls back to UTC (with a warning) when ``tz`` is ``None`` or not a known
    zone, so a bad/absent value can never crash the turn — it just resolves
    "today" in UTC, exactly as before per-user timezones existed.
    """
    if tz is None:
        return datetime.now(UTC).date()
    zone: tzinfo
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as e:
        logger.warning("Invalid user timezone; falling back to UTC", configured=tz, error=str(e))
        zone = UTC
    return datetime.now(zone).date()


@contextmanager
def bound_today(day: date) -> Iterator[None]:
    """Bind ``day`` as the request-scoped local today for the duration of the block.

    Every tool dispatched inside the block sees ``day`` via ``current_today()``.
    The previous value is restored on exit (reentrant/nesting-safe via the token).
    """
    token = _LOCAL_TODAY.set(day)
    try:
        yield
    finally:
        _LOCAL_TODAY.reset(token)


def current_today() -> date:
    """Return the turn's bound local today, or UTC today outside a bound turn."""
    return _LOCAL_TODAY.get() or datetime.now(UTC).date()
