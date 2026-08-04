"""Named reporting periods shared across analysis and summaries.

Centralizes turning a period into a concrete date range so the transactions
summary, analysis engine, etc. agree. Accepts the named periods
(``este_mes``/``mes_pasado``/``todo``) and a specific month as ``YYYY-MM``.
"""

import calendar
import re
from datetime import MAXYEAR, MINYEAR, UTC, date, datetime, timedelta
from typing import Final, Literal

# Named reporting periods accepted by the API (reuse in route query params).
PeriodName = Literal["este_mes", "mes_pasado", "todo"]

ESTE_MES: Final[str] = "este_mes"
MES_PASADO: Final[str] = "mes_pasado"
TODO: Final[str] = "todo"

# A specific month is passed as ``YYYY-MM`` (e.g. "2026-02").
_MONTH_RE: Final[re.Pattern[str]] = re.compile(r"^(\d{4})-(\d{2})$")
_MONTHS_ES: Final[tuple[str, ...]] = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

_LABELS: Final[dict[str, str]] = {
    ESTE_MES: "este mes",
    MES_PASADO: "el mes pasado",
    TODO: "todo el histórico",
}


def _parse_month(period: str) -> tuple[int, int] | None:
    """Return ``(year, month)`` if ``period`` is a valid ``YYYY-MM``, else None."""
    match = _MONTH_RE.match(period)
    if match is None:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    # Guard the month AND the year range so a value like "0000-02" falls through
    # to the lenient path instead of raising when a date is built.
    if 1 <= month <= 12 and MINYEAR <= year <= MAXYEAR:
        return year, month
    return None


def resolve_period(period: str, today: date | None = None) -> tuple[date, date]:
    """Return the (start, end) date range for a named period or a ``YYYY-MM`` month."""
    reference = today or datetime.now(UTC).date()
    month = _parse_month(period)
    if month is not None:
        year, mon = month
        last_day = calendar.monthrange(year, mon)[1]
        return date(year, mon, 1), date(year, mon, last_day)
    if period == TODO:
        return date(1970, 1, 1), reference
    if period == MES_PASADO:
        last_month_end = reference.replace(day=1) - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    return reference.replace(day=1), reference


def period_label(period: str) -> str:
    """Human-readable Spanish label for a named period or a ``YYYY-MM`` month."""
    month = _parse_month(period)
    if month is not None:
        year, mon = month
        return f"{_MONTHS_ES[mon - 1]} de {year}"
    return _LABELS.get(period, _LABELS[ESTE_MES])
