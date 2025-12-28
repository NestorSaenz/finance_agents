"""Shared module containing types, models, interfaces, and clients.

This module provides:
- types: Enums and type aliases used across the application
- models: Pydantic models for domain entities
- interfaces: Abstract Base Classes (contracts)
- clients: Concrete implementations of interfaces

Architecture:
- types.py: CategoryType, TransactionType, CurrencyType, etc.
- models.py: Transaction, Budget, Goal, Category models
- interfaces/: Abstract Base Classes (contracts)
- clients/: Concrete implementations of interfaces
"""

from app.shared.types import (
    CategoryType,
    TransactionType,
    CurrencyType,
    BudgetPeriod,
    GoalStatus,
    GoalType,
    RiskTolerance,
    VALID_CATEGORIES,
    is_valid_category,
)

__all__ = [
    # Enums
    "CategoryType",
    "TransactionType",
    "CurrencyType",
    "BudgetPeriod",
    "GoalStatus",
    "GoalType",
    "RiskTolerance",
    # Helpers
    "VALID_CATEGORIES",
    "is_valid_category",
]
