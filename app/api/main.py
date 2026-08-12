"""API Router configuration."""

from fastapi import APIRouter

from app.api.routes import (
    analysis,
    auth,
    budgets,
    cards,
    chat,
    goals,
    health,
    recurring,
    transactions,
    users,
)

api_router = APIRouter()

# Include route modules
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])
api_router.include_router(budgets.router, prefix="/budgets", tags=["Budgets"])
api_router.include_router(goals.router, prefix="/goals", tags=["Goals"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(cards.router, prefix="/cards", tags=["Cards"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
api_router.include_router(recurring.router, prefix="/recurring", tags=["Recurring"])
