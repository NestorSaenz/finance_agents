"""Serialization helpers for the persistence boundary."""

from decimal import Decimal


def decimal_to_db(value: Decimal) -> str:
    """Serialize a Decimal as a string for a Postgres ``numeric`` column.

    Sending the value as a string lets Postgres parse it exactly, avoiding the
    precision loss of JSON floats (e.g. ``float(Decimal("0.10")) != 0.10``).
    Money and other exact decimals must never be written to the DB as ``float``.
    """
    return str(value)
