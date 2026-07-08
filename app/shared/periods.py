"""Named reporting periods shared across analysis and summaries.

Centralizes turning a period name (``este_mes``/``mes_pasado``/``todo``) into a
concrete date range so the transactions summary, analysis engine, etc. agree.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Final, Literal

# Named reporting periods accepted by the API (reuse in route query params).
PeriodName = Literal["este_mes", "mes_pasado", "todo"]

ESTE_MES: Final[str] = "este_mes"
MES_PASADO: Final[str] = "mes_pasado"
TODO: Final[str] = "todo"

_LABELS: Final[dict[str, str]] = {
    ESTE_MES: "este mes",
    MES_PASADO: "el mes pasado",
    TODO: "todo el histórico",
}


def resolve_period(period: str, today: date | None = None) -> tuple[date, date]:
    """Return the (start, end) date range for a named period."""
    reference = today or datetime.now(UTC).date()
    if period == TODO:
        return date(1970, 1, 1), reference
    if period == MES_PASADO:
        last_month_end = reference.replace(day=1) - timedelta(days=1)
        return last_month_end.replace(day=1), last_month_end
    return reference.replace(day=1), reference


def period_label(period: str) -> str:
    """Human-readable Spanish label for a named period."""
    return _LABELS.get(period, _LABELS[ESTE_MES])
