"""Shared type definitions for FinanceGPT.

This module defines enums, type aliases, and custom types
used across the application for transactions, categories, and currencies.
"""

from decimal import Decimal
from enum import Enum
from typing import TypeAlias


class TransactionType(str, Enum):
    """Transaction type enumeration."""

    INCOME = "income"
    EXPENSE = "expense"


class CategoryType(str, Enum):
    """Category type enumeration (Spanish).

    These categories are used across the application for:
    - Transaction categorization (manual and AI-powered)
    - Budget allocation
    - Financial analysis and reporting
    """

    ALIMENTACION = "alimentacion"
    TRANSPORTE = "transporte"
    VIVIENDA = "vivienda"
    SERVICIOS = "servicios"
    SALUD = "salud"
    ENTRETENIMIENTO = "entretenimiento"
    EDUCACION = "educacion"
    ROPA = "ropa"
    TECNOLOGIA = "tecnologia"
    VIAJES = "viajes"
    RESTAURANTES = "restaurantes"
    COMBUSTIBLE = "combustible"
    ESTACIONAMIENTO = "estacionamiento"
    SUSCRIPCIONES = "suscripciones"
    GIMNASIO = "gimnasio"
    MASCOTAS = "mascotas"
    REGALOS = "regalos"
    IMPREVISTOS = "imprevistos"
    OTROS = "otros"


class CurrencyType(str, Enum):
    """Supported currency types."""

    MXN = "MXN"  # Mexican Peso
    COP = "COP"  # Colombian Peso
    USD = "USD"  # US Dollar
    EUR = "EUR"  # Euro


class BudgetPeriod(str, Enum):
    """Budget period types."""

    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class GoalStatus(str, Enum):
    """Financial goal status."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class GoalType(str, Enum):
    """Financial goal types."""

    SAVINGS = "savings"
    DEBT_PAYOFF = "debt_payoff"
    INVESTMENT = "investment"
    PURCHASE = "purchase"
    EMERGENCY_FUND = "emergency_fund"
    OTHER = "other"


class RiskTolerance(str, Enum):
    """User risk tolerance for investments."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


# Type aliases for domain clarity
Amount: TypeAlias = Decimal
UserId: TypeAlias = str
TransactionId: TypeAlias = str
CategoryId: TypeAlias = str
BudgetId: TypeAlias = str
GoalId: TypeAlias = str
ConversationId: TypeAlias = str
MessageId: TypeAlias = str


# Category list for validation (derived from enum)
VALID_CATEGORIES: list[str] = [category.value for category in CategoryType]


def is_valid_category(category: str) -> bool:
    """Check if a category string is valid.

    Args:
        category: Category string to validate.

    Returns:
        True if the category is valid, False otherwise.
    """
    return category.lower() in VALID_CATEGORIES
