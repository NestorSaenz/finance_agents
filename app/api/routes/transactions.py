"""Transaction endpoints for CRUD operations.

The HTTP layer only translates between DTOs and the transaction service; all
business logic lives in ``app.src.transactions``.
"""

from fastapi import APIRouter, Query

from app.core.logging import get_logger
from app.shared.periods import resolve_period
from app.shared.types import TransactionType, normalize_category
from app.src.auth.dependencies import CurrentUserId
from app.src.transactions.dependencies import TransactionServiceDep
from app.src.transactions.dto import (
    SpendingSummaryResponse,
    TransactionCreateRequest,
    TransactionListResponse,
    TransactionResponse,
)
from app.src.transactions.models import TransactionCreate

logger = get_logger(__name__)

router = APIRouter()


@router.post("", response_model=TransactionResponse)
async def create_transaction(
    request: TransactionCreateRequest,
    service: TransactionServiceDep,
    user_id: CurrentUserId,
) -> TransactionResponse:
    """Create a new transaction.

    If ``category`` is not provided it is automatically detected from the
    description using semantic similarity (Cohere embeddings + Pinecone).
    """
    transaction = TransactionCreate(
        amount=request.amount,
        description=request.description,
        transaction_type=request.transaction_type,
        transaction_date=request.transaction_date,
        category=request.category,
        payment_method=request.payment_method,
    )
    created = await service.create_transaction(transaction, user_id)
    return TransactionResponse.from_domain(created)


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    service: TransactionServiceDep,
    user_id: CurrentUserId,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    transaction_type: TransactionType | None = None,
    category: str | None = Query(default=None, description="Filter by category (known or custom)"),
    period: str | None = Query(
        default=None,
        description="Return every movement in a period ('este_mes', 'mes_pasado', "
        "'todo' or 'YYYY-MM'), newest first. Overrides pagination.",
    ),
) -> TransactionListResponse:
    """List the current user's transactions with pagination and filters."""
    normalized_category = normalize_category(category) if category else None
    # A period returns the full movement list for that range (dashboard detail),
    # so pagination does not apply.
    if period is not None:
        period_start, period_end = resolve_period(period)
        movements = await service.list_by_period(
            user_id,
            period_start=period_start,
            period_end=period_end,
            transaction_type=transaction_type,
            category=normalized_category,
        )
        return TransactionListResponse(
            transactions=[TransactionResponse.from_domain(t) for t in movements],
            total=len(movements),
            page=1,
            page_size=len(movements),
        )

    items, total = await service.list_transactions(
        user_id,
        page=page,
        page_size=page_size,
        transaction_type=transaction_type,
        category=normalized_category,
    )
    return TransactionListResponse(
        transactions=[TransactionResponse.from_domain(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/summary", response_model=SpendingSummaryResponse)
async def get_spending_summary(
    service: TransactionServiceDep,
    user_id: CurrentUserId,
    period: str = Query(
        default="este_mes",
        description="Reporting period: 'este_mes', 'mes_pasado', 'todo' or a month 'YYYY-MM'",
    ),
) -> SpendingSummaryResponse:
    """Aggregate income and expenses-by-category for the given period (dashboard)."""
    period_start, period_end = resolve_period(period)
    summary = await service.get_spending_summary(
        user_id, period_start=period_start, period_end=period_end
    )
    return SpendingSummaryResponse.from_domain(summary, period)


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: str,
    service: TransactionServiceDep,
    user_id: CurrentUserId,
) -> TransactionResponse:
    """Get a specific transaction by id (404 if it does not exist)."""
    transaction = await service.get_transaction(transaction_id, user_id)
    return TransactionResponse.from_domain(transaction)
