"""Contracts (ABCs) for the rate-limiting module."""

from abc import ABC, abstractmethod
from datetime import datetime

from app.shared.types import UserId

from .models import RateLimitBucket


class RateLimitRepositoryABC(ABC):
    """Contract for the per-user counter store."""

    @abstractmethod
    async def increment(
        self, user_id: UserId, bucket: RateLimitBucket, window_start: datetime
    ) -> int:
        """Increment the counter for ``(user_id, bucket, window_start)``.

        Returns the post-increment count. Old windows for the bucket are
        self-cleaned by the backing store.
        """


class RateLimitServiceABC(ABC):
    """Contract for enforcing chat rate limits."""

    @abstractmethod
    async def check_chat(self, user_id: UserId, *, has_image: bool) -> None:
        """Consume the chat buckets for one turn.

        Raises:
            RateLimitExceededError: When a bucket is over its configured limit.

        Returns ``None`` when the turn is allowed. Infrastructure failures never
        raise here: a broken limiter fails open (allows the request).
        """
