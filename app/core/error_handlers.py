"""Global exception handlers for FastAPI.

This module provides centralized error handling for the API.
All exceptions are converted to consistent JSON responses.

Usage:
    from app.core.error_handlers import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    ApplicationError,
    DomainError,
    FinanceGPTError,
    InfrastructureError,
    LLMRateLimitError,
)
from app.core.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers with the FastAPI app.

    Args:
        app: The FastAPI application instance.
    """

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        """Handle domain/business rule violations.

        Returns 400 Bad Request for business rule violations.
        """
        logger.warning(
            "Domain error",
            error_code=exc.code,
            message=exc.message,
            details=exc.details,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=exc.to_dict(),
        )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        request: Request, exc: ApplicationError
    ) -> JSONResponse:
        """Handle application/use case errors.

        Returns 404 for not found, 403 for unauthorized, etc.
        """
        # Determine status code based on error type
        status_code = _get_status_code_for_application_error(exc)

        logger.warning(
            "Application error",
            error_code=exc.code,
            message=exc.message,
            details=exc.details,
            path=str(request.url),
            status_code=status_code,
        )
        # Rate-limit responses carry Retry-After so clients know when to retry.
        headers: dict[str, str] = {}
        retry_after = exc.details.get("retry_after")
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)
        return JSONResponse(
            status_code=status_code,
            content=exc.to_dict(),
            headers=headers,
        )

    @app.exception_handler(LLMRateLimitError)
    async def llm_rate_limit_handler(
        request: Request, exc: LLMRateLimitError
    ) -> JSONResponse:
        """Handle LLM rate limit errors.

        Returns 429 Too Many Requests with retry-after header.
        """
        logger.warning(
            "LLM rate limit exceeded",
            provider=exc.details.get("provider"),
            retry_after=exc.details.get("retry_after"),
            path=str(request.url),
        )

        headers = {}
        if exc.details.get("retry_after"):
            headers["Retry-After"] = str(exc.details["retry_after"])

        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=exc.to_dict(),
            headers=headers,
        )

    @app.exception_handler(InfrastructureError)
    async def infrastructure_error_handler(
        request: Request, exc: InfrastructureError
    ) -> JSONResponse:
        """Handle infrastructure/external service errors.

        Returns 503 Service Unavailable for external service failures.
        """
        logger.error(
            "Infrastructure error",
            error_code=exc.code,
            message=exc.message,
            details=exc.details,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": exc.code,
                "message": "An external service is temporarily unavailable. Please try again later.",
                "details": {},  # Don't expose internal details
            },
        )

    @app.exception_handler(FinanceGPTError)
    async def financegpt_error_handler(
        request: Request, exc: FinanceGPTError
    ) -> JSONResponse:
        """Handle any other FinanceGPT errors.

        Catch-all for custom exceptions not handled above.
        """
        logger.error(
            "Unhandled FinanceGPT error",
            error_code=exc.code,
            message=exc.message,
            details=exc.details,
            path=str(request.url),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unexpected exceptions.

        Logs the full exception and returns a generic error message.
        """
        logger.exception(
            "Unexpected error",
            error_type=type(exc).__name__,
            message=str(exc),
            path=str(request.url),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred. Please try again later.",
                "details": {},
            },
        )


def _get_status_code_for_application_error(exc: ApplicationError) -> int:
    """Determine HTTP status code based on error code.

    Args:
        exc: The application error.

    Returns:
        Appropriate HTTP status code.
    """
    # Not Found errors
    not_found_codes = {
        "TRANSACTION_NOT_FOUND",
        "BUDGET_NOT_FOUND",
        "GOAL_NOT_FOUND",
        "CATEGORY_NOT_FOUND",
        "CARD_NOT_FOUND",
        "CARD_TEMPLATE_NOT_FOUND",
        "USER_NOT_FOUND",
    }
    if exc.code in not_found_codes:
        return status.HTTP_404_NOT_FOUND

    # Authentication errors
    if exc.code in {"UNAUTHORIZED", "INVALID_CREDENTIALS"}:
        return status.HTTP_401_UNAUTHORIZED

    # Unauthorized/Forbidden errors
    if exc.code == "UNAUTHORIZED_ACCESS":
        return status.HTTP_403_FORBIDDEN

    # Rate limiting
    if exc.code == "RATE_LIMIT_EXCEEDED":
        return status.HTTP_429_TOO_MANY_REQUESTS

    # Default to 400 Bad Request
    return status.HTTP_400_BAD_REQUEST
