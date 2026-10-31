"""Domain models for the rate-limiting module."""

from app.shared.types import RateLimitBucket

# The enum lives in ``app.shared.types`` (core errors need it too); re-exported here so
# the module's callers keep importing it from its domain models.
__all__ = ["RateLimitBucket"]
