"""Recurring-transaction endpoints: list (dashboard) and the daily run job.

``GET /recurring`` is user-scoped (authenticated). ``POST /recurring/run`` is a
SYSTEM endpoint driven by Cloud Scheduler, not a user: it is protected by a shared
secret header instead of a user token, so it never resolves a ``CurrentUserId``.
"""

import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from app.core.logging import get_logger
from app.src.auth.dependencies import CurrentUserId
from app.src.recurring.clock import recurring_today
from app.src.recurring.dependencies import RecurringServiceDep
from app.src.recurring.dto import (
    RecurringListResponse,
    RecurringResponse,
    RecurringRunResponse,
)

logger = get_logger(__name__)

router = APIRouter()


async def verify_recurring_secret(
    x_recurring_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Guard the system run endpoint with a shared secret.

    Rejects the request when the secret is not configured or the header does not
    match it, so an unset secret fails closed (the job can never run unprotected).
    """
    secret = settings.RECURRING_RUN_SECRET
    # Constant-time compare so a timing side-channel can't probe the secret. An
    # unset secret (or missing header) still fails closed.
    if (
        not secret
        or x_recurring_secret is None
        or not hmac.compare_digest(x_recurring_secret, secret)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing recurring run secret",
        )


@router.get("", response_model=RecurringListResponse)
async def list_recurring(
    service: RecurringServiceDep,
    user_id: CurrentUserId,
) -> RecurringListResponse:
    """List the current user's recurring templates (for the dashboard)."""
    items = await service.list_recurring(user_id)
    return RecurringListResponse(
        recurring=[RecurringResponse.from_domain(r) for r in items],
        total=len(items),
    )


@router.post(
    "/run",
    response_model=RecurringRunResponse,
    dependencies=[Depends(verify_recurring_secret)],
)
async def run_recurring(service: RecurringServiceDep) -> RecurringRunResponse:
    """Materialize every due recurring template into real transactions.

    System endpoint: called daily by Cloud Scheduler with the shared secret
    header. Returns the number of transactions created.
    """
    created = await service.run_due(recurring_today())
    logger.info("Recurring run completed", created=created)
    return RecurringRunResponse(created=created)
