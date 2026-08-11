"""Unit tests for the rate-limit service (window/bucket logic + fail-open)."""

from datetime import datetime

import pytest

from app.core.exceptions import RateLimitExceededError
from app.src.ratelimit.interfaces import RateLimitRepositoryABC
from app.src.ratelimit.models import RateLimitBucket
from app.src.ratelimit.services.rate_limit_service import RateLimitService


class RecordingRepo(RateLimitRepositoryABC):
    """Repo double that records calls and returns scripted counts (or raises)."""

    def __init__(self, counts: list[int] | None = None, raises: bool = False) -> None:
        self.calls: list[tuple[RateLimitBucket, datetime]] = []
        self._counts = list(counts or [])
        self._raises = raises

    async def increment(
        self, user_id: str, bucket: RateLimitBucket, window_start: datetime
    ) -> int:
        self.calls.append((bucket, window_start))
        if self._raises:
            raise RuntimeError("db down")
        return self._counts.pop(0) if self._counts else 1


def _service(
    repo: RateLimitRepositoryABC,
    *,
    per_minute: int = 10,
    per_day: int = 100,
    images_per_day: int = 10,
    enabled: bool = True,
) -> RateLimitService:
    return RateLimitService(
        repo,
        per_minute=per_minute,
        per_day=per_day,
        images_per_day=images_per_day,
        enabled=enabled,
    )


class TestWindows:
    async def test_minute_window_truncated_to_the_minute(self) -> None:
        repo = RecordingRepo(counts=[1, 1])
        await _service(repo).check_chat("u1", has_image=False)

        minute_bucket, minute_start = repo.calls[0]
        assert minute_bucket is RateLimitBucket.CHAT_MINUTE
        assert minute_start.second == 0 and minute_start.microsecond == 0

    async def test_day_window_truncated_to_midnight(self) -> None:
        repo = RecordingRepo(counts=[1, 1])
        await _service(repo).check_chat("u1", has_image=False)

        _, day_start = repo.calls[1]
        assert (day_start.hour, day_start.minute, day_start.second, day_start.microsecond) == (
            0,
            0,
            0,
            0,
        )


class TestBucketSelection:
    async def test_text_turn_consumes_chat_day(self) -> None:
        repo = RecordingRepo(counts=[1, 1])
        await _service(repo).check_chat("u1", has_image=False)
        assert [bucket for bucket, _ in repo.calls] == [
            RateLimitBucket.CHAT_MINUTE,
            RateLimitBucket.CHAT_DAY,
        ]

    async def test_image_turn_consumes_image_day(self) -> None:
        repo = RecordingRepo(counts=[1, 1])
        await _service(repo).check_chat("u1", has_image=True)
        assert [bucket for bucket, _ in repo.calls] == [
            RateLimitBucket.CHAT_MINUTE,
            RateLimitBucket.IMAGE_DAY,
        ]


class TestThresholds:
    async def test_under_limit_passes(self) -> None:
        repo = RecordingRepo(counts=[5, 5])
        await _service(repo).check_chat("u1", has_image=False)  # no raise
        assert len(repo.calls) == 2

    async def test_over_minute_raises_before_touching_day(self) -> None:
        repo = RecordingRepo(counts=[11])  # first (minute) call already over
        with pytest.raises(RateLimitExceededError) as exc_info:
            await _service(repo, per_minute=10).check_chat("u1", has_image=False)

        assert exc_info.value.details["bucket"] == "chat_minute"
        assert exc_info.value.details["limit"] == 10
        assert 1 <= exc_info.value.details["retry_after"] <= 60
        assert len(repo.calls) == 1  # day bucket never consumed

    async def test_over_daily_text_raises(self) -> None:
        repo = RecordingRepo(counts=[1, 101])
        with pytest.raises(RateLimitExceededError) as exc_info:
            await _service(repo, per_day=100).check_chat("u1", has_image=False)

        assert exc_info.value.details["bucket"] == "chat_day"
        assert 1 <= exc_info.value.details["retry_after"] <= 86_400

    async def test_over_daily_image_raises(self) -> None:
        repo = RecordingRepo(counts=[1, 11])
        with pytest.raises(RateLimitExceededError) as exc_info:
            await _service(repo, images_per_day=10).check_chat("u1", has_image=True)

        assert exc_info.value.details["bucket"] == "image_day"
        assert exc_info.value.details["limit"] == 10


class TestResilience:
    async def test_disabled_is_a_noop(self) -> None:
        repo = RecordingRepo(counts=[999])
        await _service(repo, enabled=False).check_chat("u1", has_image=False)
        assert repo.calls == []  # limiter never touches the store when disabled

    async def test_fails_open_when_repo_raises(self) -> None:
        repo = RecordingRepo(raises=True)
        # A broken store must not raise: the turn is allowed through.
        await _service(repo).check_chat("u1", has_image=False)
        assert len(repo.calls) == 2  # both increments attempted, both swallowed
