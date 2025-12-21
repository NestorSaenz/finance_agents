# Core Module - Configuration, Logging, Exceptions, Validators
"""Core module for FinanceGPT.

This module provides cross-cutting concerns:
- Configuration management (config.py)
- Logging setup (logging.py)
- Domain exceptions (exceptions.py)
- Domain validators (validators.py)
- API error handlers (error_handlers.py)
"""

from app.core.config import settings
from app.core.error_handlers import register_exception_handlers
from app.core.exceptions import (
    ApplicationError,
    DomainError,
    FinanceGPTError,
    InfrastructureError,
)
from app.core.validators import (
    validate_amount,
    validate_transaction_type,
)

__all__ = [
    # Config
    "settings",
    # Exceptions
    "FinanceGPTError",
    "DomainError",
    "ApplicationError",
    "InfrastructureError",
    # Error Handlers
    "register_exception_handlers",
    # Validators
    "validate_amount",
    "validate_transaction_type",
]
