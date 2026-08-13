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


class PaymentMethod(str, Enum):
    """How an expense was paid.

    Only the credit-vs-cash distinction matters for financial control:
    ``EFECTIVO`` covers real money that already left the account (cash, debit,
    transfer); ``CREDITO`` is deferred money owed on a credit card.
    """

    EFECTIVO = "efectivo"
    CREDITO = "credito"


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


class MovementKind(str, Enum):
    """Kind of a unified movement across the transaction/card/goal ledgers.

    A movement the user sees in the dashboard's list can live in three tables:
    a transaction (income/expense), a card payment, or a goal contribution
    (a positive aporte or a negative retiro). This tags which one a found
    candidate is, so the agent routes deletion to the right tool.
    """

    EXPENSE = "expense"
    INCOME = "income"
    CARD_PAYMENT = "card_payment"
    GOAL_CONTRIBUTION = "goal_contribution"
    GOAL_WITHDRAWAL = "goal_withdrawal"


# Type aliases for domain clarity
Amount: TypeAlias = Decimal
UserId: TypeAlias = str
# A category is free text: known values come from ``CategoryType`` (the canonical
# vocabulary), but users can define their own (e.g. imported from a spreadsheet).
Category: TypeAlias = str
TransactionId: TypeAlias = str
CategoryId: TypeAlias = str
BudgetId: TypeAlias = str
GoalId: TypeAlias = str
CardId: TypeAlias = str
ConversationId: TypeAlias = str
MessageId: TypeAlias = str


# Category list for validation (derived from enum)
VALID_CATEGORIES: list[str] = [category.value for category in CategoryType]


def is_valid_category(category: str) -> bool:
    """Check if a category string is one of the canonical (known) categories.

    Args:
        category: Category string to validate.

    Returns:
        True if the category is a known ``CategoryType`` value, False otherwise.
        Note: custom (user-defined) categories are valid to store even though
        this returns False for them.
    """
    return category.lower() in VALID_CATEGORIES


def normalize_category(value: str) -> str:
    """Normalize a category to its stored form: trimmed, lowercased, single-spaced.

    Custom categories (e.g. from an imported spreadsheet) are preserved as-is
    apart from this normalization; an empty value falls back to ``"otros"``.
    """
    normalized = " ".join(value.split()).lower()
    return normalized or CategoryType.OTROS.value
