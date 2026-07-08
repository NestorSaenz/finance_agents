"""Contract (ABC) for the financial analysis module."""

from abc import ABC, abstractmethod

from app.shared.types import UserId

from .models import FinancialSnapshot


class AnalysisServiceABC(ABC):
    """Contract for building a holistic financial snapshot."""

    @abstractmethod
    async def snapshot(self, user_id: UserId, period: str) -> FinancialSnapshot:
        """Aggregate the user's finances for ``period`` into a snapshot."""
