"""Data Transfer Objects for the analysis API layer."""

from decimal import Decimal

from pydantic import BaseModel, Field


class AccumulatedSurplusResponse(BaseModel):
    """Free (unearmarked) cash accumulated up to the selected month-end."""

    accumulated_surplus: Decimal = Field(
        ...,
        description="Cumulative disponible real up to the period's month-end "
        "(income − cash − card payments − goal contributions). Carries over month "
        "to month; can be negative. Decimal serialized as string.",
    )
