"""Unit tests for the request-scoped local-today clock."""

from datetime import UTC, date, datetime

from app.shared.clock import bound_today, current_today, local_date, local_today


def test_local_date_resolves_the_date_in_the_given_timezone() -> None:
    # 03:00 UTC on Jan 2: still Jan 1 in Bogota (UTC-5 -> 22:00 Jan 1) but already
    # Jan 2 in Tokyo (UTC+9 -> 12:00 Jan 2). One instant, two calendar days.
    instant = datetime(2026, 1, 2, 3, 0, tzinfo=UTC)
    assert local_date(instant, "America/Bogota") == date(2026, 1, 1)
    assert local_date(instant, "Asia/Tokyo") == date(2026, 1, 2)


def test_local_date_falls_back_to_utc_on_invalid_zone() -> None:
    instant = datetime(2026, 1, 2, 3, 0, tzinfo=UTC)
    assert local_date(instant, "Mars/Phobos") == date(2026, 1, 2)


def test_local_date_falls_back_to_utc_on_none() -> None:
    instant = datetime(2026, 1, 2, 3, 0, tzinfo=UTC)
    assert local_date(instant, None) == date(2026, 1, 2)


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
