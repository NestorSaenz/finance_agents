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
from datetime import UTC, date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.logging import get_logger

logger = get_logger(__name__)

# A document date is plausible when it is at most this far in the future...
STATEMENT_FUTURE_TOLERANCE: Final[timedelta] = timedelta(days=7)
# ...and at most ~3 months in the past (a statement spans ~2 cycles; nobody loads old data).
STATEMENT_MAX_AGE: Final[timedelta] = timedelta(days=90)

# The user's local "today" for the current chat turn. ``None`` when no turn is
# bound, so readers fall back to UTC (see ``current_today``).
_LOCAL_TODAY: ContextVar[date | None] = ContextVar("local_today", default=None)


def local_date(instant: datetime, tz: str | None) -> date:
    """Return the calendar date of ``instant`` in IANA timezone ``tz``.

    ``instant`` must be timezone-aware. Falls back to the UTC date (with a
    warning) when ``tz`` is ``None`` or not a known zone, so a bad/absent value
    can never crash the caller — it just resolves the date in UTC, exactly as
    before per-user timezones existed.
    """
    if tz is None:
        return instant.astimezone(UTC).date()
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as e:
        logger.warning("Invalid user timezone; falling back to UTC", configured=tz, error=str(e))
        return instant.astimezone(UTC).date()
    return instant.astimezone(zone).date()


def local_today(tz: str | None) -> date:
    """Return the current calendar day in IANA timezone ``tz``.

    Thin wrapper over :func:`local_date` for "now", so there is one timezone
    conversion implementation. Same UTC fallback semantics.
    """
    return local_date(datetime.now(UTC), tz)


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


def resolve_statement_date(extracted: date, today: date) -> date:
    """Correct the year of a date read from a statement/receipt image.

    Documents often omit the year and the vision model guesses one (2023/2024),
    so a date far from ``today`` is always a misread year. A plausible date (not
    more than a week ahead, not older than ~3 months) is returned unchanged.
    Otherwise its month/day are kept and the year becomes ``today.year`` or the
    previous one, whichever lands on or before ``today + 7 days`` closest to today
    (Feb 29 falls back to Feb 28 in a non-leap year).
    """
    latest = today + STATEMENT_FUTURE_TOLERANCE
    if today - STATEMENT_MAX_AGE <= extracted <= latest:
        return extracted
    this_year = _same_day_in_year(extracted, today.year)
    return this_year if this_year <= latest else _same_day_in_year(extracted, today.year - 1)


def _same_day_in_year(value: date, year: int) -> date:
    """``value``'s month/day in ``year``; Feb 29 becomes Feb 28 when not a leap year."""
    try:
        return value.replace(year=year)
    except ValueError:
        return value.replace(year=year, day=28)
