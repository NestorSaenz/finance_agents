"""Unit tests for the credit-card billing-cycle math."""

from datetime import date

import pytest

from app.src.cards.cycle import (
    UpcomingPayment,
    compute_cycle,
    next_payment_date,
    payment_date_in_month,
    upcoming_payment,
)


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


class TestUpcomingPayment:
    """The next payment due on/after a day may settle an already-closed statement."""

    def test_before_payment_day_this_month_pays_closed_statement(self) -> None:
        # cutoff 15 / pay 5, Jul 3: the May 16-Jun 15 statement is due Jul 5.
        up = upcoming_payment(15, 5, date(2026, 7, 3))
        assert up == UpcomingPayment(
            date(2026, 7, 5), date(2026, 5, 16), date(2026, 6, 15), statement_closed=True
        )

    def test_after_payment_day_before_cutoff_pays_open_cycle(self) -> None:
        # cutoff 15 / pay 5, Jul 10: Jul 5 passed -> the open Jun 16-Jul 15 cycle, Aug 5.
        up = upcoming_payment(15, 5, date(2026, 7, 10))
        assert up == UpcomingPayment(
            date(2026, 8, 5), date(2026, 6, 16), date(2026, 7, 15), statement_closed=False
        )

    @pytest.mark.parametrize("today", [date(2026, 9, 30), date(2026, 10, 1)])
    def test_after_cutoff_before_payment_day_astrid_rappi(self, today: date) -> None:
        # Real report: cutoff 19 / pay 2. The Aug 20-Sep 19 statement is due Oct 2,
        # not the open cycle's Nov 2.
        up = upcoming_payment(19, 2, today)
        assert up == UpcomingPayment(
            date(2026, 10, 2), date(2026, 8, 20), date(2026, 9, 19), statement_closed=True
        )

    def test_due_today_is_still_upcoming(self) -> None:
        up = upcoming_payment(19, 2, date(2026, 10, 2))
        assert up.due_date == date(2026, 10, 2)
        assert up.statement_closed is True

    def test_day_after_due_moves_to_open_cycle(self) -> None:
        up = upcoming_payment(19, 2, date(2026, 10, 3))
        assert up == UpcomingPayment(
            date(2026, 11, 2), date(2026, 9, 20), date(2026, 10, 19), statement_closed=False
        )

    @pytest.mark.parametrize(
        ("today", "expected"),
        [
            # Before the cutoff: the closed Aug 10 statement was due Aug 26 (passed),
            # so the next due date is the open Aug 11-Sep 10 cycle's Sep 26.
            (
                date(2026, 9, 5),
                UpcomingPayment(
                    date(2026, 9, 26), date(2026, 8, 11), date(2026, 9, 10), False
                ),
            ),
            # After the Sep 10 cutoff, before Sep 26: that statement is due Sep 26.
            (
                date(2026, 9, 15),
                UpcomingPayment(
                    date(2026, 9, 26), date(2026, 8, 11), date(2026, 9, 10), True
                ),
            ),
            # After Sep 26: the open Sep 11-Oct 10 cycle, due Oct 26.
            (
                date(2026, 9, 28),
                UpcomingPayment(
                    date(2026, 10, 26), date(2026, 9, 11), date(2026, 10, 10), False
                ),
            ),
        ],
    )
    def test_payment_day_after_cutoff_day_bbva(
        self, today: date, expected: UpcomingPayment
    ) -> None:
        # Astrid's BBVA: cutoff 10 / pay 26 (payment in the SAME month as the cutoff).
        assert upcoming_payment(10, 26, today) == expected

    def test_year_boundary(self) -> None:
        # cutoff 20 / pay 5, Dec 28: the Nov 21-Dec 20 statement is due Jan 5 next year.
        up = upcoming_payment(20, 5, date(2026, 12, 28))
        assert up == UpcomingPayment(
            date(2027, 1, 5), date(2026, 11, 21), date(2026, 12, 20), statement_closed=True
        )

    def test_payment_day_31_clamps_in_february(self) -> None:
        # cutoff 15 / pay 31, Feb 20: the Jan 16-Feb 15 statement is due Feb 28.
        up = upcoming_payment(15, 31, date(2026, 2, 20))
        assert up == UpcomingPayment(
            date(2026, 2, 28), date(2026, 1, 16), date(2026, 2, 15), statement_closed=True
        )

    def test_cutoff_31_clamps_closed_statement_period(self) -> None:
        # cutoff 31 / pay 10, Mar 5: the closed statement ends Feb 28 (clamped) and
        # starts Feb 1 (Jan 31 + 1); it's due Mar 10.
        up = upcoming_payment(31, 10, date(2026, 3, 5))
        assert up == UpcomingPayment(
            date(2026, 3, 10), date(2026, 2, 1), date(2026, 2, 28), statement_closed=True
        )


class TestPaymentDateInMonth:
    def test_is_payment_day_of_the_viewed_month(self) -> None:
        # September view, payment day 2 -> Sep 2 (not Oct/Nov).
        assert payment_date_in_month(2, date(2026, 9, 30)) == date(2026, 9, 2)

    def test_clamps_to_the_month_length(self) -> None:
        assert payment_date_in_month(31, date(2026, 2, 28)) == date(2026, 2, 28)
        assert payment_date_in_month(31, date(2026, 9, 30)) == date(2026, 9, 30)

    def test_leap_year_february(self) -> None:
        assert payment_date_in_month(31, date(2028, 2, 29)) == date(2028, 2, 29)
