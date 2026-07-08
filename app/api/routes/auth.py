"""Authentication endpoints: signup and login (Supabase Auth)."""

from fastapi import APIRouter

from app.core.logging import get_logger
from app.src.auth.dependencies import AuthServiceDep
from app.src.auth.dto import (
    LoginRequest,
    RefreshRequest,
    SessionResponse,
    SignupRequest,
)

logger = get_logger(__name__)

router = APIRouter()


@router.post("/signup", response_model=SessionResponse)
async def signup(request: SignupRequest, auth_service: AuthServiceDep) -> SessionResponse:
    """Register a new user and return their session tokens."""
    session = await auth_service.sign_up(request.email, request.password, request.full_name)
    return SessionResponse.from_domain(session)


@router.post("/login", response_model=SessionResponse)
async def login(request: LoginRequest, auth_service: AuthServiceDep) -> SessionResponse:
    """Authenticate a user and return their session tokens."""
    session = await auth_service.sign_in(request.email, request.password)
    return SessionResponse.from_domain(session)


@router.post("/refresh", response_model=SessionResponse)
async def refresh(request: RefreshRequest, auth_service: AuthServiceDep) -> SessionResponse:
    """Exchange a refresh token for a fresh session (keeps the user logged in)."""
    session = await auth_service.refresh_session(request.refresh_token)
    return SessionResponse.from_domain(session)
