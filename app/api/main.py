"""API Router configuration."""

from fastapi import APIRouter

from app.api.routes import chat, health, transactions

api_router = APIRouter()

# Include route modules
api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(transactions.router, prefix="/transactions", tags=["Transactions"])

# TODO: Add more routes as modules are implemented
# api_router.include_router(budgets.router, prefix="/budgets", tags=["Budgets"])
# api_router.include_router(goals.router, prefix="/goals", tags=["Goals"])
