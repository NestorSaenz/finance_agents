"""Data Transfer Objects for the transactions API layer."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.shared.types import (
    Category,
    CategoryType,
    PaymentMethod,
    TransactionType,
    normalize_category,
)

from .constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from .models import SpendingSummary, Transaction


class TransactionCreateRequest(BaseModel):
    """Request body for creating a transaction."""

    amount: Decimal = Field(..., gt=0, description="Transaction amount", examples=[50000])
    description: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Transaction description",
        examples=["Almuerzo con colegas"],
    )
    transaction_type: TransactionType = Field(
        ..., description="Type of transaction", examples=[TransactionType.EXPENSE]
    )
    category: Category | None = Field(
        default=None,
        description=(
            "Category (auto-detected from the description if omitted). Known values "
            "come from the canonical set but custom categories are accepted."
        ),
        examples=[CategoryType.RESTAURANTES.value],
    )
    payment_method: PaymentMethod | None = Field(
        default=None,
        description="How it was paid (cash vs credit); omit if unknown",
        examples=[PaymentMethod.EFECTIVO],
    )
    transaction_date: date = Field(
        ..., description="Date of the transaction", examples=["2024-12-20"]
    )

    @field_validator("category")
    @classmethod
    def _normalize_category(cls, value: str | None) -> str | None:
        return normalize_category(value) if value else None


class TransactionResponse(BaseModel):
    """Response body for a single transaction."""

    id: str = Field(..., description="Unique transaction identifier")
    amount: Decimal = Field(..., description="Transaction amount")
    description: str = Field(..., description="Transaction description")
    transaction_type: TransactionType = Field(..., description="Income or expense")
    category: Category = Field(..., description="Transaction category")
    payment_method: PaymentMethod | None = Field(
        default=None, description="How it was paid (cash vs credit), if known"
    )
    transaction_date: date = Field(..., description="Transaction date")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")

    @classmethod
    def from_domain(cls, transaction: Transaction) -> "TransactionResponse":
        """Build the API response from a domain transaction."""
        return cls(
            id=transaction.id,
            amount=transaction.amount,
            description=transaction.description,
            transaction_type=transaction.transaction_type,
            category=transaction.category,
            payment_method=transaction.payment_method,
            transaction_date=transaction.transaction_date,
            created_at=transaction.created_at.isoformat(),
        )


class TransactionListResponse(BaseModel):
    """Response body for a paginated list of transactions."""

    transactions: list[TransactionResponse] = Field(
        default_factory=list, description="List of transactions"
    )
    total: int = Field(..., ge=0, description="Total transaction count")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(
        ..., ge=1, le=MAX_PAGE_SIZE, description="Items per page", examples=[DEFAULT_PAGE_SIZE]
    )


class CategorySpendingResponse(BaseModel):
    """Expense total + share for one category (dashboard chart)."""

    category: Category
    amount: Decimal
    percentage: float


class SpendingSummaryResponse(BaseModel):
    """Aggregated spending for a period (powers the dashboard)."""

    period: str
    total_income: Decimal
    total_expenses: Decimal
    balance: Decimal
    by_category: list[CategorySpendingResponse]
    credit_expenses: Decimal
    cash_expenses: Decimal

    @classmethod
    def from_domain(cls, summary: SpendingSummary, period: str) -> "SpendingSummaryResponse":
        total = summary.total_expenses
        by_category = [
            CategorySpendingResponse(
                category=c.category,
                amount=c.amount,
                percentage=float(c.amount / total * 100) if total > 0 else 0.0,
            )
            for c in summary.by_category
        ]
        return cls(
            period=period,
            total_income=summary.total_income,
            total_expenses=summary.total_expenses,
            balance=summary.total_income - summary.total_expenses,
            by_category=by_category,
            credit_expenses=summary.credit_expenses,
            cash_expenses=summary.cash_expenses,
        )
