"""Transaction endpoints for CRUD operations."""

from datetime import date
from decimal import Decimal
from enum import Enum

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class TransactionType(str, Enum):
    """Transaction type enumeration."""

    INCOME = "income"
    EXPENSE = "expense"


class CategoryType(str, Enum):
    """Category type enumeration."""

    FOOD = "food"
    TRANSPORT = "transport"
    ENTERTAINMENT = "entertainment"
    UTILITIES = "utilities"
    HEALTH = "health"
    EDUCATION = "education"
    SHOPPING = "shopping"
    SALARY = "salary"
    OTHER = "other"


class TransactionCreateRequest(BaseModel):
    """Request model for creating a transaction."""

    amount: Decimal = Field(..., gt=0, description="Transaction amount")
    description: str = Field(..., min_length=1, max_length=500, description="Transaction description")
    transaction_type: TransactionType = Field(..., description="Type of transaction")
    category: CategoryType | None = Field(None, description="Category (auto-detected if not provided)")
    transaction_date: date = Field(..., description="Date of the transaction")


class TransactionResponse(BaseModel):
    """Response model for a transaction."""

    id: str
    amount: Decimal
    description: str
    transaction_type: TransactionType
    category: CategoryType
    transaction_date: date
    created_at: str


class TransactionListResponse(BaseModel):
    """Response model for transaction list."""

    transactions: list[TransactionResponse]
    total: int
    page: int
    page_size: int


@router.post("", response_model=TransactionResponse)
async def create_transaction(request: TransactionCreateRequest) -> TransactionResponse:
    """Create a new transaction.

    If category is not provided, it will be automatically detected
    using the AI categorizer agent.

    Args:
        request: Transaction data

    Returns:
        Created transaction with assigned category
    """
    logger.info(
        "Creating transaction",
        amount=float(request.amount),
        type=request.transaction_type,
    )

    # TODO: Implement actual transaction creation with Supabase
    # TODO: Implement auto-categorization with Cohere embeddings

    return TransactionResponse(
        id="tx_placeholder",
        amount=request.amount,
        description=request.description,
        transaction_type=request.transaction_type,
        category=request.category or CategoryType.OTHER,
        transaction_date=request.transaction_date,
        created_at="2024-12-20T00:00:00Z",
    )


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    page: int = 1,
    page_size: int = 20,
    transaction_type: TransactionType | None = None,
    category: CategoryType | None = None,
) -> TransactionListResponse:
    """List transactions for the current user.

    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page
        transaction_type: Filter by transaction type
        category: Filter by category

    Returns:
        Paginated list of transactions
    """
    logger.info(
        "Listing transactions",
        page=page,
        page_size=page_size,
        type_filter=transaction_type,
        category_filter=category,
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
        transaction_id: Transaction identifier

    Returns:
        Transaction details
    """
    logger.info("Getting transaction", transaction_id=transaction_id)

    # TODO: Implement actual transaction retrieval with Supabase

    return TransactionResponse(
        id=transaction_id,
        amount=Decimal("0"),
        description="Placeholder",
        transaction_type=TransactionType.EXPENSE,
        category=CategoryType.OTHER,
        transaction_date=date.today(),
        created_at="2024-12-20T00:00:00Z",
    )
