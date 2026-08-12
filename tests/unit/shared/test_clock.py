"""Unit tests for the request-scoped local-today clock."""

from datetime import UTC, date, datetime

from app.shared.clock import bound_today, current_today, local_today


def test_local_today_uses_the_given_timezone() -> None:
    # Bogota is UTC-5; its calendar day matches datetime.now(ZoneInfo) — assert it
    # equals the same instant resolved through the helper (no fixed date needed).
    from zoneinfo import ZoneInfo

    assert local_today("America/Bogota") == datetime.now(ZoneInfo("America/Bogota")).date()


def test_local_today_falls_back_to_utc_on_invalid_zone() -> None:
    assert local_today("Mars/Phobos") == datetime.now(UTC).date()


def test_local_today_falls_back_to_utc_on_none() -> None:
    assert local_today(None) == datetime.now(UTC).date()


def test_bound_today_sets_and_resets() -> None:
    frozen = date(2026, 8, 11)
    assert current_today() != frozen or current_today() == datetime.now(UTC).date()
    with bound_today(frozen):
        assert current_today() == frozen
    # After the block the binding is gone: back to UTC today.
    assert current_today() == datetime.now(UTC).date()


def test_current_today_outside_bind_is_utc_today() -> None:
    assert current_today() == datetime.now(UTC).date()


def test_bound_today_nests_and_restores_outer() -> None:
    outer = date(2026, 1, 1)
    inner = date(2026, 2, 2)
    with bound_today(outer):
        assert current_today() == outer
        with bound_today(inner):
            assert current_today() == inner
        # Inner unwinds to the outer binding, not straight to UTC.
        assert current_today() == outer
