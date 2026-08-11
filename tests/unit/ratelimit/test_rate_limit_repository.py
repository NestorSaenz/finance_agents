"""Unit tests for the Supabase-backed rate-limit repository."""

from datetime import UTC, datetime

from app.src.ratelimit.constants import CHECK_RATE_LIMIT_RPC
from app.src.ratelimit.models import RateLimitBucket
from app.src.ratelimit.repositories.rate_limit_repository import RateLimitRepository
from tests.fakes import FakeDatabase


class TestIncrement:
    async def test_calls_rpc_and_returns_post_increment_count(self) -> None:
        db = FakeDatabase()
        db.rpc_result = [7]  # scalar count the check_rate_limit RPC returns
        repo = RateLimitRepository(db)
        window = datetime(2026, 8, 11, 10, 30, tzinfo=UTC)

        count = await repo.increment("u1", RateLimitBucket.CHAT_MINUTE, window)

        assert count == 7
        name, params = db.rpc_calls[-1]
        assert name == CHECK_RATE_LIMIT_RPC
        assert params == {
            "p_user_id": "u1",
            "p_bucket": "chat_minute",
            "p_window_start": window.isoformat(),
        }

    async def test_passes_image_day_bucket_value(self) -> None:
        db = FakeDatabase()
        db.rpc_result = [1]
        repo = RateLimitRepository(db)

        await repo.increment(
            "u1", RateLimitBucket.IMAGE_DAY, datetime(2026, 8, 11, tzinfo=UTC)
        )

        _, params = db.rpc_calls[-1]
        assert params["p_bucket"] == "image_day"
