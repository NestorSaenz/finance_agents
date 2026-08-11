"""Domain exceptions for FinanceGPT.

This module defines custom exceptions following DDD principles.
All exceptions are organized by domain/bounded context.

Exception Hierarchy:
- FinanceGPTError (base)
  - DomainError (business rule violations)
  - ApplicationError (use case errors)
  - InfrastructureError (external service errors)

Usage:
    from app.core.exceptions import TransactionNotFoundError

    raise TransactionNotFoundError(transaction_id="abc-123")
"""

from typing import Any

# =============================================================================
# Base Exceptions
# =============================================================================


class FinanceGPTError(Exception):
    """Base exception for all FinanceGPT errors.

    All custom exceptions inherit from this class.
    Provides consistent error formatting and metadata.
    """

    def __init__(
        self,
        message: str,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert exception to dictionary for API responses."""
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class DomainError(FinanceGPTError):
    """Base exception for domain/business rule violations.

    Use when a business rule is violated.
    Examples: Invalid amount, budget exceeded, invalid category.
    """

    pass


class ApplicationError(FinanceGPTError):
    """Base exception for application/use case errors.

    Use when a use case cannot be completed.
    Examples: Resource not found, permission denied, conflict.
    """

    pass


class InfrastructureError(FinanceGPTError):
    """Base exception for infrastructure/external service errors.

    Use when an external service fails.
    Examples: Database error, LLM API error, vector store error.
    """

    pass


# =============================================================================
# Domain Errors - Transaction
# =============================================================================


class InvalidAmountError(DomainError):
    """Raised when a transaction amount is invalid."""

    def __init__(self, amount: float, reason: str = "Amount must be positive") -> None:
        super().__init__(
            message=f"Invalid amount: {amount}. {reason}",
            code="INVALID_AMOUNT",
            details={"amount": amount, "reason": reason},
        )


class InvalidTransactionTypeError(DomainError):
    """Raised when a transaction type is invalid."""

    def __init__(self, transaction_type: str) -> None:
        super().__init__(
            message=f"Invalid transaction type: {transaction_type}. Must be 'income' or 'expense'",
            code="INVALID_TRANSACTION_TYPE",
            details={"type": transaction_type, "valid_types": ["income", "expense"]},
        )


class TransactionNotFoundError(ApplicationError):
    """Raised when a transaction is not found."""

    def __init__(self, transaction_id: str) -> None:
        super().__init__(
            message=f"Transaction not found: {transaction_id}",
            code="TRANSACTION_NOT_FOUND",
            details={"transaction_id": transaction_id},
        )


# =============================================================================
# Domain Errors - Budget
# =============================================================================


class BudgetExceededError(DomainError):
    """Raised when a transaction would exceed the budget."""

    def __init__(
        self,
        budget_name: str,
        budget_amount: float,
        current_spent: float,
        transaction_amount: float,
    ) -> None:
        remaining = budget_amount - current_spent
        super().__init__(
            message=f"Budget '{budget_name}' would be exceeded. Remaining: {remaining}, Transaction: {transaction_amount}",
            code="BUDGET_EXCEEDED",
            details={
                "budget_name": budget_name,
                "budget_amount": budget_amount,
                "current_spent": current_spent,
                "remaining": remaining,
                "transaction_amount": transaction_amount,
            },
        )


class InvalidBudgetPeriodError(DomainError):
    """Raised when budget period is invalid."""

    def __init__(self, start_date: str, end_date: str) -> None:
        super().__init__(
            message=f"Invalid budget period: start ({start_date}) must be before end ({end_date})",
            code="INVALID_BUDGET_PERIOD",
            details={"start_date": start_date, "end_date": end_date},
        )


class BudgetNotFoundError(ApplicationError):
    """Raised when a budget is not found."""

    def __init__(self, budget_id: str) -> None:
        super().__init__(
            message=f"Budget not found: {budget_id}",
            code="BUDGET_NOT_FOUND",
            details={"budget_id": budget_id},
        )


# =============================================================================
# Domain Errors - Goal
# =============================================================================


class InvalidGoalTargetError(DomainError):
    """Raised when a goal target amount is invalid."""

    def __init__(self, target_amount: float) -> None:
        super().__init__(
            message=f"Invalid goal target: {target_amount}. Must be greater than 0",
            code="INVALID_GOAL_TARGET",
            details={"target_amount": target_amount},
        )


class GoalAlreadyCompletedError(DomainError):
    """Raised when trying to modify a completed goal."""

    def __init__(self, goal_id: str, goal_name: str) -> None:
        super().__init__(
            message=f"Goal '{goal_name}' is already completed and cannot be modified",
            code="GOAL_ALREADY_COMPLETED",
            details={"goal_id": goal_id, "goal_name": goal_name},
        )


class GoalNotFoundError(ApplicationError):
    """Raised when a goal is not found."""

    def __init__(self, goal_id: str) -> None:
        super().__init__(
            message=f"Goal not found: {goal_id}",
            code="GOAL_NOT_FOUND",
            details={"goal_id": goal_id},
        )


# =============================================================================
# Domain Errors - Category
# =============================================================================


class InvalidCategoryError(DomainError):
    """Raised when a category is invalid for the transaction type."""

    def __init__(self, category: str, transaction_type: str) -> None:
        super().__init__(
            message=f"Category '{category}' is not valid for transaction type '{transaction_type}'",
            code="INVALID_CATEGORY",
            details={"category": category, "transaction_type": transaction_type},
        )


class CategoryNotFoundError(ApplicationError):
    """Raised when a category is not found."""

    def __init__(self, category_id: str) -> None:
        super().__init__(
            message=f"Category not found: {category_id}",
            code="CATEGORY_NOT_FOUND",
            details={"category_id": category_id},
        )


class SystemCategoryModificationError(DomainError):
    """Raised when trying to modify a system category."""

    def __init__(self, category_name: str) -> None:
        super().__init__(
            message=f"Cannot modify system category: '{category_name}'",
            code="SYSTEM_CATEGORY_MODIFICATION",
            details={"category_name": category_name},
        )


# =============================================================================
# Domain Errors - Card
# =============================================================================


class CardNotFoundError(ApplicationError):
    """Raised when a user card is not found."""

    def __init__(self, card_id: str) -> None:
        super().__init__(
            message=f"Card not found: {card_id}",
            code="CARD_NOT_FOUND",
            details={"card_id": card_id},
        )


class CardTemplateNotFoundError(ApplicationError):
    """Raised when a card template is not found."""

    def __init__(self, template_id: str) -> None:
        super().__init__(
            message=f"Card template not found: {template_id}",
            code="CARD_TEMPLATE_NOT_FOUND",
            details={"template_id": template_id},
        )


class InvalidCardFieldError(DomainError):
    """Raised when a card field value is invalid."""

    def __init__(self, field_name: str, field_type: str, value: Any) -> None:
        super().__init__(
            message=f"Invalid value for field '{field_name}' (type: {field_type}): {value}",
            code="INVALID_CARD_FIELD",
            details={"field_name": field_name, "field_type": field_type, "value": str(value)},
        )


# =============================================================================
# Domain Errors - User
# =============================================================================


class UserNotFoundError(ApplicationError):
    """Raised when a user is not found."""

    def __init__(self, user_id: str) -> None:
        super().__init__(
            message=f"User not found: {user_id}",
            code="USER_NOT_FOUND",
            details={"user_id": user_id},
        )


class UserProfileIncompleteError(DomainError):
    """Raised when user profile is missing required information."""

    def __init__(self, missing_fields: list[str]) -> None:
        super().__init__(
            message=f"User profile is incomplete. Missing: {', '.join(missing_fields)}",
            code="USER_PROFILE_INCOMPLETE",
            details={"missing_fields": missing_fields},
        )


class UnauthorizedAccessError(ApplicationError):
    """Raised when user tries to access resources they don't own."""

    def __init__(self, resource_type: str, resource_id: str) -> None:
        super().__init__(
            message=f"Unauthorized access to {resource_type}: {resource_id}",
            code="UNAUTHORIZED_ACCESS",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


# =============================================================================
# Domain Errors - Auth
# =============================================================================


class AuthenticationError(ApplicationError):
    """Raised when a token is missing, invalid, or expired."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message=message, code="UNAUTHORIZED")


class InvalidCredentialsError(ApplicationError):
    """Raised when sign-in credentials are wrong."""

    def __init__(self) -> None:
        super().__init__(message="Invalid email or password", code="INVALID_CREDENTIALS")


class RegistrationError(DomainError):
    """Raised when sign-up fails (e.g. email already registered, weak password)."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Registration failed: {reason}",
            code="REGISTRATION_FAILED",
            details={"reason": reason},
        )


# =============================================================================
# Application Errors - Rate Limiting
# =============================================================================


class RateLimitExceededError(ApplicationError):
    """Raised when a user exceeds their allowed chat rate for a bucket."""

    def __init__(self, bucket: str, limit: int, retry_after: int) -> None:
        super().__init__(
            message=(
                "Has enviado demasiados mensajes; espera un momento y vuelve a intentarlo."
            ),
            code="RATE_LIMIT_EXCEEDED",
            details={"bucket": bucket, "limit": limit, "retry_after": retry_after},
        )


# =============================================================================
# Infrastructure Errors - LLM
# =============================================================================


class LLMError(InfrastructureError):
    """Base exception for LLM-related errors."""

    pass


class LLMRateLimitError(LLMError):
    """Raised when LLM rate limit is exceeded."""

    def __init__(self, provider: str, retry_after: int | None = None) -> None:
        message = f"Rate limit exceeded for {provider}"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(
            message=message,
            code="LLM_RATE_LIMIT",
            details={"provider": provider, "retry_after": retry_after},
        )


class LLMConnectionError(LLMError):
    """Raised when LLM connection fails."""

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(
            message=f"Failed to connect to {provider}: {reason}",
            code="LLM_CONNECTION_ERROR",
            details={"provider": provider, "reason": reason},
        )


class LLMResponseError(LLMError):
    """Raised when LLM returns an invalid response."""

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(
            message=f"Invalid response from {provider}: {reason}",
            code="LLM_RESPONSE_ERROR",
            details={"provider": provider, "reason": reason},
        )


# =============================================================================
# Infrastructure Errors - Vector Store
# =============================================================================


class VectorStoreError(InfrastructureError):
    """Base exception for vector store errors."""

    pass


class EmbeddingError(VectorStoreError):
    """Raised when embedding generation fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Failed to generate embedding: {reason}",
            code="EMBEDDING_ERROR",
            details={"reason": reason},
        )


class VectorSearchError(VectorStoreError):
    """Raised when vector search fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Vector search failed: {reason}",
            code="VECTOR_SEARCH_ERROR",
            details={"reason": reason},
        )


# =============================================================================
# Infrastructure Errors - Database
# =============================================================================


class DatabaseError(InfrastructureError):
    """Base exception for database errors."""

    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Database connection failed: {reason}",
            code="DATABASE_CONNECTION_ERROR",
            details={"reason": reason},
        )


class DatabaseQueryError(DatabaseError):
    """Raised when a database query fails."""

    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            message=f"Database {operation} failed: {reason}",
            code="DATABASE_QUERY_ERROR",
            details={"operation": operation, "reason": reason},
        )


# =============================================================================
# Convenience exports
# =============================================================================

__all__ = [
    # Base
    "FinanceGPTError",
    "DomainError",
    "ApplicationError",
    "InfrastructureError",
    # Transaction
    "InvalidAmountError",
    "InvalidTransactionTypeError",
    "TransactionNotFoundError",
    # Budget
    "BudgetExceededError",
    "InvalidBudgetPeriodError",
    "BudgetNotFoundError",
    # Goal
    "InvalidGoalTargetError",
    "GoalAlreadyCompletedError",
    "GoalNotFoundError",
    # Category
    "InvalidCategoryError",
    "CategoryNotFoundError",
    "SystemCategoryModificationError",
    # Card
    "CardNotFoundError",
    "CardTemplateNotFoundError",
    "InvalidCardFieldError",
    # User
    "UserNotFoundError",
    "UserProfileIncompleteError",
    "UnauthorizedAccessError",
    # Rate Limiting
    "RateLimitExceededError",
    # LLM
    "LLMError",
    "LLMRateLimitError",
    "LLMConnectionError",
    "LLMResponseError",
    # Vector Store
    "VectorStoreError",
    "EmbeddingError",
    "VectorSearchError",
    # Database
    "DatabaseError",
    "DatabaseConnectionError",
    "DatabaseQueryError",
]
