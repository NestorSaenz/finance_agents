"""Unit tests for the credit-card billing-cycle math."""

from datetime import date

from app.src.cards.cycle import compute_cycle, next_payment_date


class TestComputeCycle:
    def test_before_cutoff_uses_current_month_end(self) -> None:
        # cutoff 15, today Jul 3 -> open cycle Jun 16 .. Jul 15
        start, end = compute_cycle(15, date(2026, 7, 3))
        assert start == date(2026, 6, 16)
        assert end == date(2026, 7, 15)

    def test_after_cutoff_rolls_to_next_month(self) -> None:
        # cutoff 15, today Jul 20 -> open cycle Jul 16 .. Aug 15
        start, end = compute_cycle(15, date(2026, 7, 20))
        assert start == date(2026, 7, 16)
        assert end == date(2026, 8, 15)

    def test_on_cutoff_day_closes_that_day(self) -> None:
        start, end = compute_cycle(15, date(2026, 7, 15))
        assert end == date(2026, 7, 15)
        assert start == date(2026, 6, 16)

    def test_cutoff_31_clamps_in_february(self) -> None:
        # cutoff 31 clamps to the last day of the month (Feb 28 in 2026)
        start, end = compute_cycle(31, date(2026, 2, 10))
        assert end == date(2026, 2, 28)
        assert start == date(2026, 2, 1)  # Jan 31 + 1 day


class TestNextPaymentDate:
    def test_payment_before_cutoff_rolls_to_next_month(self) -> None:
        # payment day 5, cycle closes Jul 15 -> pay Aug 5
        assert next_payment_date(5, date(2026, 7, 15)) == date(2026, 8, 5)

    def test_payment_after_cutoff_same_month(self) -> None:
        # payment day 20, cycle closes Jul 15 -> pay Jul 20
        assert next_payment_date(20, date(2026, 7, 15)) == date(2026, 7, 20)
