"""Rate-limit service: enforces per-user chat allowances.

Every chat turn consumes the per-minute burst bucket. A text turn also consumes
the daily-text bucket; an image turn consumes the daily-image bucket instead
(image turns are heavier: they hit Gemini vision).

The limiter is resilient: if the counter store errors, it logs a warning and
fails open (allows the request). Only an over-limit turn raises
``RateLimitExceededError`` — a broken limiter must never take chat down.
"""

import math
from datetime import UTC, datetime, timedelta

from app.core.exceptions import RateLimitExceededError
from app.core.logging import get_logger
from app.shared.types import UserId

from ..interfaces import RateLimitRepositoryABC, RateLimitServiceABC
from ..models import RateLimitBucket

logger = get_logger(__name__)


class RateLimitService(RateLimitServiceABC):
    """Consumes the chat rate-limit buckets and enforces their thresholds."""

    def __init__(
        self,
        repository: RateLimitRepositoryABC,
        *,
        per_minute: int,
        per_day: int,
        images_per_day: int,
        enabled: bool,
    ) -> None:
        self._repository = repository
        self._per_minute = per_minute
        self._per_day = per_day
        self._images_per_day = images_per_day
        self._enabled = enabled

    async def check_chat(self, user_id: UserId, *, has_image: bool) -> None:
        if not self._enabled:
            return

        now = datetime.now(UTC)
        minute_start = now.replace(second=0, microsecond=0)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Burst guard: every turn (text or image) consumes the per-minute bucket.
        minute_count = await self._increment(
            user_id, RateLimitBucket.CHAT_MINUTE, minute_start
        )
        if minute_count is not None and minute_count > self._per_minute:
            raise RateLimitExceededError(
                bucket=RateLimitBucket.CHAT_MINUTE.value,
                limit=self._per_minute,
                retry_after=_seconds_until(minute_start + timedelta(minutes=1), now),
            )

        # Daily allowance: image turns draw from their own (heavier) bucket.
        day_bucket = RateLimitBucket.IMAGE_DAY if has_image else RateLimitBucket.CHAT_DAY
        day_limit = self._images_per_day if has_image else self._per_day
        day_count = await self._increment(user_id, day_bucket, day_start)
        if day_count is not None and day_count > day_limit:
            raise RateLimitExceededError(
                bucket=day_bucket.value,
                limit=day_limit,
                retry_after=_seconds_until(day_start + timedelta(days=1), now),
            )

    async def _increment(
        self, user_id: UserId, bucket: RateLimitBucket, window_start: datetime
    ) -> int | None:
        """Increment a bucket, failing open (return ``None``) on infra errors."""
        try:
            return await self._repository.increment(user_id, bucket, window_start)
        except Exception as e:  # noqa: BLE001 - a broken limiter must never break chat (fail open).
            logger.warning(
                "Rate limit check failed; allowing request",
                bucket=bucket.value,
                error=str(e),
            )
            return None


def _seconds_until(target: datetime, now: datetime) -> int:
    """Whole seconds until ``target`` (at least 1, for the ``Retry-After`` header)."""
    return max(1, math.ceil((target - now).total_seconds()))
