"""Unit tests for the shared reporting periods (named + specific month)."""

from datetime import date

from app.shared.periods import period_label, resolve_period

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
