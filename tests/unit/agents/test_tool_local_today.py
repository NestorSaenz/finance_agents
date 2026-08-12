"""The tool date sites default omitted dates to the turn's bound local today."""

from datetime import date

from app.agents.tools.transaction_tools import _period_range, _to_date
from app.shared.clock import bound_today, current_today
from app.shared.periods import resolve_period

FROZEN = date(2026, 8, 11)


def test_to_date_defaults_to_bound_today() -> None:
    with bound_today(FROZEN):
        # Omitted / unparseable transaction_date falls back to the local day.
        assert _to_date({}) == FROZEN
        assert _to_date("not-a-date") == FROZEN
    # An explicit ISO date is honored regardless of the binding.
    with bound_today(FROZEN):
        assert _to_date("2025-01-02") == date(2025, 1, 2)


def test_period_range_uses_bound_today() -> None:
    with bound_today(FROZEN):
        start, end = _period_range("este_mes")
    assert start == date(2026, 8, 1)
    assert end == FROZEN


def test_resolve_period_uses_bound_today() -> None:
    with bound_today(FROZEN):
        start, end = resolve_period("este_mes", today=current_today())
    # August 2026 window from the frozen local day.
    assert start == date(2026, 8, 1)
    assert end == date(2026, 8, 31)
