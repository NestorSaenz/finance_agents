"""Pytest configuration and fixtures."""

from collections.abc import Callable
from datetime import datetime
from datetime import tzinfo as TzInfo

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI application."""
    return TestClient(app)


# 2026-10-31 23:30 in Bogotá (UTC-5) is already 2026-11-01 04:30 UTC: the instant where
# a UTC "today" and the Colombian "today" differ (and the month flips).
BOGOTA_LATE_NIGHT = datetime.fromisoformat("2026-10-31T23:30:00-05:00")


@pytest.fixture
def freeze_now(monkeypatch: pytest.MonkeyPatch) -> Callable[[datetime], None]:
    """Freeze the clock module's ``datetime.now`` at a given aware instant."""

    def _freeze(instant: datetime) -> None:
        class _Frozen(datetime):
            @classmethod
            def now(cls, tz: TzInfo | None = None) -> datetime:  # type: ignore[override]
                return instant if tz is None else instant.astimezone(tz)

        monkeypatch.setattr("app.shared.clock.datetime", _Frozen)

    return _freeze
