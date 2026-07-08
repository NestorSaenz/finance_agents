"""Domain validators for FinanceGPT.

This module provides validation functions following DDD principles.
Validators ensure business rules are enforced at the domain level.

Usage:
    from app.core.validators import validate_amount, validate_transaction_type

    validate_amount(100.50)  # OK
    validate_amount(-50)     # Raises InvalidAmountError
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.core.exceptions import (
    InvalidAmountError,
    InvalidBudgetPeriodError,
    InvalidCardFieldError,
    InvalidGoalTargetError,
    InvalidTransactionTypeError,
)

# =============================================================================
# Transaction Validators
# =============================================================================


def validate_amount(amount: float | Decimal, allow_zero: bool = False) -> float:
    """Validate that an amount is positive.

    Args:
        amount: The amount to validate.
        allow_zero: Whether zero is a valid amount.

    Returns:
        The validated amount as float.

    Raises:
        InvalidAmountError: If amount is negative or (zero when not allowed).
    """
    amount_float = float(amount)

    if amount_float < 0:
        raise InvalidAmountError(amount_float, "Amount cannot be negative")

    if not allow_zero and amount_float == 0:
        raise InvalidAmountError(amount_float, "Amount cannot be zero")

    return amount_float


def validate_transaction_type(transaction_type: str) -> str:
    """Validate that transaction type is valid.

    Args:
        transaction_type: The type to validate.

    Returns:
        The validated type (lowercase).

    Raises:
        InvalidTransactionTypeError: If type is not 'income' or 'expense'.
    """
    normalized = transaction_type.lower().strip()

    if normalized not in ("income", "expense"):
        raise InvalidTransactionTypeError(transaction_type)

    return normalized


def validate_currency(currency: str) -> str:
    """Validate and normalize currency code.

    Args:
        currency: The currency code to validate.

    Returns:
        The validated currency code (uppercase).

    Raises:
        ValueError: If currency code is invalid.
    """
    normalized = currency.upper().strip()

    # Common currencies supported
    valid_currencies = {
        "MXN",
        "USD",
        "EUR",
        "GBP",
        "CAD",
        "AUD",
        "JPY",
        "CNY",
        "BRL",
        "ARS",
        "COP",
        "CLP",
        "PEN",
    }

    if normalized not in valid_currencies:
        raise ValueError(f"Invalid currency: {currency}. Supported: {', '.join(sorted(valid_currencies))}")

    return normalized


# =============================================================================
# Budget Validators
# =============================================================================


def validate_budget_period(start_date: date, end_date: date | None) -> None:
    """Validate that budget period is valid.

    Args:
        start_date: The start date of the budget period.
        end_date: The end date (optional, None means ongoing).

    Raises:
        InvalidBudgetPeriodError: If end_date is before start_date.
    """
    if end_date is not None and end_date < start_date:
        raise InvalidBudgetPeriodError(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )


def validate_alert_threshold(threshold: float) -> float:
    """Validate budget alert threshold.

    Args:
        threshold: The threshold percentage (0-100).

    Returns:
        The validated threshold.

    Raises:
        ValueError: If threshold is out of range.
    """
    if threshold < 0 or threshold > 100:
        raise ValueError(f"Alert threshold must be between 0 and 100, got: {threshold}")

    return threshold


# =============================================================================
# Goal Validators
# =============================================================================


def validate_goal_target(target_amount: float | Decimal) -> float:
    """Validate that goal target is positive.

    Args:
        target_amount: The target amount to validate.

    Returns:
        The validated target as float.

    Raises:
        InvalidGoalTargetError: If target is not positive.
    """
    target_float = float(target_amount)

    if target_float <= 0:
        raise InvalidGoalTargetError(target_float)

    return target_float


def validate_goal_progress(current_amount: float, target_amount: float) -> float:
    """Calculate and validate goal progress percentage.

    Args:
        current_amount: Current amount saved.
        target_amount: Target amount.

    Returns:
        Progress percentage (0-100+, can exceed 100 if over-saved).
    """
    if target_amount <= 0:
        return 0.0

    progress = (current_amount / target_amount) * 100
    return round(progress, 2)


def validate_goal_status(status: str) -> str:
    """Validate goal status.

    Args:
        status: The status to validate.

    Returns:
        The validated status.

    Raises:
        ValueError: If status is invalid.
    """
    valid_statuses = {"active", "paused", "completed", "cancelled"}
    normalized = status.lower().strip()

    if normalized not in valid_statuses:
        raise ValueError(f"Invalid goal status: {status}. Valid: {', '.join(valid_statuses)}")

    return normalized


# =============================================================================
# Card Field Validators
# =============================================================================


def validate_card_field_value(
    field_name: str,
    field_type: str,
    value: Any,
    options: list[str] | None = None,
    required: bool = False,
) -> Any:
    """Validate a card field value based on its type.

    Args:
        field_name: The name of the field.
        field_type: The type of the field.
        value: The value to validate.
        options: Valid options for 'select' type.
        required: Whether the field is required.

    Returns:
        The validated and possibly converted value.

    Raises:
        InvalidCardFieldError: If value is invalid for the field type.
    """
    # Handle required fields
    if required and (value is None or value == ""):
        raise InvalidCardFieldError(field_name, field_type, value)

    # Skip validation for empty optional fields
    if value is None or value == "":
        return None

    # Validate based on type
    try:
        if field_type == "text":
            return str(value)

        elif field_type == "number":
            return float(value)

        elif field_type == "currency":
            amount = float(value)
            if amount < 0:
                raise InvalidCardFieldError(field_name, field_type, value)
            return amount

        elif field_type == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "si", "sí")
            return bool(value)

        elif field_type == "date":
            if isinstance(value, date):
                return value.isoformat()
            # Assume ISO format string
            date.fromisoformat(str(value))
            return str(value)

        elif field_type == "select":
            if options and str(value) not in options:
                raise InvalidCardFieldError(field_name, field_type, value)
            return str(value)

        elif field_type == "tags":
            if isinstance(value, list):
                return [str(v) for v in value]
            return [str(value)]

        else:
            # Unknown type, pass through
            return value

    except (ValueError, TypeError) as e:
        raise InvalidCardFieldError(field_name, field_type, value) from e


# =============================================================================
# General Validators
# =============================================================================


def validate_uuid(value: str, field_name: str = "id") -> str:
    """Validate that a string is a valid UUID.

    Args:
        value: The string to validate.
        field_name: The name of the field (for error messages).

    Returns:
        The validated UUID string.

    Raises:
        ValueError: If the string is not a valid UUID.
    """
    import uuid

    try:
        # This will raise if invalid
        uuid.UUID(value)
        return value
    except (ValueError, AttributeError) as e:
        raise ValueError(f"Invalid UUID for {field_name}: {value}") from e


def validate_email(email: str) -> str:
    """Validate email format.

    Args:
        email: The email to validate.

    Returns:
        The validated email (lowercase, stripped).

    Raises:
        ValueError: If email format is invalid.
    """
    import re

    normalized = email.lower().strip()

    # Simple email regex
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    if not re.match(pattern, normalized):
        raise ValueError(f"Invalid email format: {email}")

    return normalized


def validate_percentage(value: float, field_name: str = "percentage") -> float:
    """Validate that a value is a valid percentage (0-100).

    Args:
        value: The percentage to validate.
        field_name: The name of the field (for error messages).

    Returns:
        The validated percentage.

    Raises:
        ValueError: If not in range 0-100.
    """
    if value < 0 or value > 100:
        raise ValueError(f"{field_name} must be between 0 and 100, got: {value}")

    return value


def validate_positive_integer(value: int, field_name: str = "value") -> int:
    """Validate that a value is a positive integer.

    Args:
        value: The integer to validate.
        field_name: The name of the field (for error messages).

    Returns:
        The validated integer.

    Raises:
        ValueError: If not a positive integer.
    """
    if not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer, got: {value}")

    return value


# =============================================================================
# Convenience exports
# =============================================================================

__all__ = [
    # Transaction
    "validate_amount",
    "validate_transaction_type",
    "validate_currency",
    # Budget
    "validate_budget_period",
    "validate_alert_threshold",
    # Goal
    "validate_goal_target",
    "validate_goal_progress",
    "validate_goal_status",
    # Card
    "validate_card_field_value",
    # General
    "validate_uuid",
    "validate_email",
    "validate_percentage",
    "validate_positive_integer",
]
