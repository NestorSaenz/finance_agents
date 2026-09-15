"""Unit tests for the shared reporting periods (named + specific month)."""

from datetime import date

from app.shared.periods import (
    is_valid_period,
    period_label,
    recent_months,
    resolve_period,
)

REF = date(2026, 8, 4)


class TestResolvePeriod:
    def test_specific_month_spans_the_whole_month(self) -> None:
        assert resolve_period("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))

    def test_leap_february(self) -> None:
        assert resolve_period("2024-02") == (date(2024, 2, 1), date(2024, 2, 29))

    def test_este_mes_spans_the_whole_current_month(self) -> None:
        # The full month, not 1 -> today: a bill dated the 15th must still count
        # when today is the 4th (otherwise the month reads as zero spending).
        assert resolve_period("este_mes", today=REF) == (date(2026, 8, 1), date(2026, 8, 31))

    def test_este_mes_uses_the_real_last_day_of_a_short_month(self) -> None:
        # February (non-31-day) exercises calendar.monthrange in the named branch.
        assert resolve_period("este_mes", today=date(2026, 2, 10)) == (
            date(2026, 2, 1),
            date(2026, 2, 28),
        )

    def test_mes_pasado(self) -> None:
        assert resolve_period("mes_pasado", today=REF) == (date(2026, 7, 1), date(2026, 7, 31))

    def test_todo_is_open_from_epoch_through_end_of_current_month(self) -> None:
        # Like "este_mes", "todo" ends at the last day of the current month so a
        # bill dated later in the month is not hidden from the historical view.
        assert resolve_period("todo", today=REF) == (date(1970, 1, 1), date(2026, 8, 31))

    def test_invalid_month_falls_back_to_este_mes(self) -> None:
        # 2026-13 is not a real month -> treated as the default (este_mes).
        assert resolve_period("2026-13", today=REF) == (date(2026, 8, 1), date(2026, 8, 31))

    def test_out_of_range_year_falls_back_without_raising(self) -> None:
        # "0000-02" matches the YYYY-MM shape but year 0 is out of date range;
        # it must degrade to the default, never raise (would be an HTTP 500).
        assert resolve_period("0000-02", today=REF) == (date(2026, 8, 1), date(2026, 8, 31))


class TestPeriodLabel:
    def test_month_label_in_spanish(self) -> None:
        assert period_label("2026-02") == "febrero de 2026"

    def test_named_labels(self) -> None:
        assert period_label("todo") == "todo el histórico"
        assert period_label("este_mes") == "este mes"


class TestIsValidPeriod:
    def test_accepts_named_periods(self) -> None:
        assert all(is_valid_period(p) for p in ("este_mes", "mes_pasado", "todo"))

    def test_accepts_a_real_month(self) -> None:
        assert is_valid_period("2026-06")

    def test_rejects_unknown_or_malformed(self) -> None:
        # These must be REJECTED by callers, not silently resolved to este_mes.
        assert not any(
            is_valid_period(p) for p in ("", "junio", "2026-13", "2026/06", "0000-02")
        )


class TestRecentMonths:
    def test_returns_the_window_oldest_first_ending_this_month(self) -> None:
        assert recent_months(3, today=REF) == ["2026-06", "2026-07", "2026-08"]

    def test_crosses_the_year_boundary(self) -> None:
        assert recent_months(3, today=date(2026, 2, 10)) == [
            "2025-12",
            "2026-01",
            "2026-02",
        ]

    def test_single_month_is_the_current_one(self) -> None:
        assert recent_months(1, today=REF) == ["2026-08"]

    def test_every_key_resolves_to_that_calendar_month(self) -> None:
        # The keys feed resolve_period unchanged, so a trend reuses exactly the
        # same windows a single-month query uses.
        assert resolve_period(recent_months(2, today=REF)[0]) == (
            date(2026, 7, 1),
            date(2026, 7, 31),
        )
