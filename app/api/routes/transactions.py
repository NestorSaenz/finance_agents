"""Transaction endpoints for CRUD operations.

This module provides REST API endpoints for managing financial transactions.
DTOs are defined here for API layer, importing shared types from domain.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.shared.types import CategoryType, TransactionType

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# DTOs (Data Transfer Objects) for API Layer
# =============================================================================


class TransactionCreateRequest(BaseModel):
    """Request model for creating a transaction.

    Attributes:
        amount: Transaction amount (must be positive).
        description: Description of the transaction.
        transaction_type: Whether this is income or expense.
        category: Category (optional, auto-detected if not provided).
        transaction_date: Date when the transaction occurred.
    """

    amount: Decimal = Field(
        ...,
        gt=0,
        description="Transaction amount",
        examples=[50000],
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Transaction description",
        examples=["Almuerzo con colegas"],
    )
    transaction_type: TransactionType = Field(
        ...,
        description="Type of transaction",
        examples=[TransactionType.EXPENSE],
    )
    category: CategoryType | None = Field(
        default=None,
        description="Category (auto-detected if not provided)",
        examples=[CategoryType.RESTAURANTES],
    )
    transaction_date: date = Field(
        ...,
        description="Date of the transaction",
        examples=["2024-12-20"],
    )


class TransactionResponse(BaseModel):
    """Response model for a transaction.

    Attributes:
        id: Unique transaction identifier.
        amount: Transaction amount.
        description: Transaction description.
        transaction_type: Income or expense.
        category: Assigned category.
        transaction_date: Date of the transaction.
        created_at: Creation timestamp.
    """

    id: str = Field(..., description="Unique transaction identifier")
    amount: Decimal = Field(..., description="Transaction amount")
    description: str = Field(..., description="Transaction description")
    transaction_type: TransactionType = Field(..., description="Income or expense")
    category: CategoryType = Field(..., description="Transaction category")
    transaction_date: date = Field(..., description="Transaction date")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")


class TransactionListResponse(BaseModel):
    """Response model for paginated transaction list.

    Attributes:
        transactions: List of transactions.
        total: Total number of transactions.
        page: Current page number.
        page_size: Number of items per page.
    """

    transactions: list[TransactionResponse] = Field(
        default_factory=list, description="List of transactions"
    )
    total: int = Field(..., ge=0, description="Total transaction count")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Items per page")


# =============================================================================
# Endpoints
# =============================================================================


@router.post("", response_model=TransactionResponse)
async def create_transaction(request: TransactionCreateRequest) -> TransactionResponse:
    """Create a new transaction.

    If category is not provided, it will be automatically detected
    using the AI categorizer agent with Cohere embeddings.

    Args:
        request: Transaction creation data.

    Returns:
        Created transaction with assigned category.
    """
    logger.info(
        "Creating transaction",
        amount=float(request.amount),
        type=request.transaction_type.value,
    )

    # TODO: Implement actual transaction creation with Supabase
    # TODO: Implement auto-categorization with Cohere embeddings

    return TransactionResponse(
        id="tx_placeholder",
        amount=request.amount,
        description=request.description,
        transaction_type=request.transaction_type,
        category=request.category or CategoryType.OTROS,
        transaction_date=request.transaction_date,
        created_at=datetime.now(UTC).isoformat(),
    )


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    page: int = Field(default=1, ge=1, description="Page number"),
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page"),
    transaction_type: TransactionType | None = None,
    category: CategoryType | None = None,
) -> TransactionListResponse:
    """List transactions for the current user.

    Supports pagination and filtering by type and category.

    Args:
        page: Page number (1-indexed).
        page_size: Number of items per page (max 100).
        transaction_type: Filter by income or expense.
        category: Filter by category.

    Returns:
        Paginated list of transactions.
    """
    logger.info(
        "Listing transactions",
        page=page,
        page_size=page_size,
        type_filter=transaction_type.value if transaction_type else None,
        category_filter=category.value if category else None,
    )

    # TODO: Implement actual transaction listing with Supabase

    return TransactionListResponse(
        transactions=[],
        total=0,
        page=page,
        page_size=page_size,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(transaction_id: str) -> TransactionResponse:
    """Get a specific transaction by ID.

    Args:
        transaction_id: Unique transaction identifier.

    Returns:
        Transaction details.

    Raises:
        HTTPException: 404 if transaction not found.
    """
    logger.info("Getting transaction", transaction_id=transaction_id)

    # TODO: Implement actual transaction retrieval with Supabase
    # TODO: Raise HTTPException(404) if not found

    return TransactionResponse(
        id=transaction_id,
        amount=Decimal("0"),
        description="Placeholder",
        transaction_type=TransactionType.EXPENSE,
        category=CategoryType.OTROS,
        transaction_date=date.today(),
        created_at=datetime.now(UTC).isoformat(),
    )
