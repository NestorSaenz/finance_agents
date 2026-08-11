"""Supabase-backed rate-limit counter store (data access only)."""

from collections.abc import Sequence
from datetime import datetime

from app.core.logging import get_logger
from app.shared.interfaces.database import DatabaseInterface
from app.shared.types import UserId

from ..constants import CHECK_RATE_LIMIT_RPC
from ..interfaces import RateLimitRepositoryABC
from ..models import RateLimitBucket

logger = get_logger(__name__)


class RateLimitRepository(RateLimitRepositoryABC):
    """Increments per-user counters via the ``check_rate_limit`` RPC (migration 012).

    The Postgres function self-cleans old windows, upserts the counter and returns
    the post-increment count in a single round trip; the threshold comparison lives
    in the service, so the repository only reports the current count.
    """

    def __init__(self, db: DatabaseInterface) -> None:
        self._db = db

    async def increment(
        self, user_id: UserId, bucket: RateLimitBucket, window_start: datetime
    ) -> int:
        result = await self._db.execute_rpc(
            CHECK_RATE_LIMIT_RPC,
            {
                "p_user_id": user_id,
                "p_bucket": bucket.value,
                "p_window_start": window_start.isoformat(),
            },
        )
        return _parse_count(result.data)


def _parse_count(data: Sequence[object]) -> int:
    """Extract the integer count returned by the ``check_rate_limit`` RPC."""
    if not data:
        raise ValueError("check_rate_limit returned no rows")
    value: object = data[0]
    # A scalar function result may arrive raw (int) or wrapped as a single-column row.
    if isinstance(value, dict):
        value = next(iter(value.values()), None)
    if not isinstance(value, (int, str)):
        raise ValueError(f"check_rate_limit returned a non-numeric count: {value!r}")
    return int(value)
