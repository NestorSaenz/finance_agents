"""Parsing helpers for the persistence boundary (DB row -> domain values).

Shared by the transaction/budget/goal repositories so the coercion rules stay
consistent (previously each repo had its own slightly-divergent copies).

Inputs are typed ``object`` (not ``Any``): a raw DB value has an unknown type,
and ``object`` forces each helper to narrow it explicitly before use.
"""

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import TypeVar

E = TypeVar("E", bound=Enum)


def parse_decimal(value: object, default: Decimal = Decimal("0")) -> Decimal:
    """Coerce a DB value to Decimal, or ``default`` if it isn't numeric."""
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return default


def parse_optional_decimal(value: object) -> Decimal | None:
    """Like :func:`parse_decimal` but ``None`` passes through as ``None``."""
    return None if value is None else parse_decimal(value)


def parse_enum(enum_cls: type[E], value: object, default: E) -> E:
    """Coerce a value to ``enum_cls``, or ``default`` if it isn't a valid member."""
    try:
        return enum_cls(value)
    except ValueError:
        return default


def parse_date(value: object) -> date:
    """Coerce a DB value to a ``date`` (today if missing/invalid)."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return datetime.now(UTC).date()
    return datetime.now(UTC).date()


def parse_optional_date(value: object) -> date | None:
    """Parse an optional date; ``None`` or an invalid value yields ``None``.

    Unlike :func:`parse_date`, an absent/invalid optional date is not fabricated
    as "today" — it stays ``None``.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def parse_datetime(value: object) -> datetime:
    """Coerce a DB value to a timezone-aware ``datetime`` (now if invalid)."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC)
