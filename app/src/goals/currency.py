"""The currency a new goal gets when none is given."""

from app.core.config import settings
from app.core.logging import get_logger
from app.shared.types import CurrencyType

logger = get_logger(__name__)


def default_goal_currency() -> CurrencyType:
    """``settings.DEFAULT_CURRENCY`` validated against the supported currencies.

    Read at call time (never frozen at import). A configured value the goals module
    doesn't support falls back to COP with a warning instead of breaking goal creation.
    """
    try:
        return CurrencyType(settings.DEFAULT_CURRENCY)
    except ValueError:
        logger.warning(
            "Unsupported DEFAULT_CURRENCY for goals; falling back to COP",
            currency=settings.DEFAULT_CURRENCY,
        )
        return CurrencyType.COP
