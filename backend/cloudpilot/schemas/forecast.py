"""Forecast schemas."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import Field

from cloudpilot.schemas.common import APISchema, ResponseSchema


class ForecastPoint(ResponseSchema):
    ds: date
    yhat: float
    yhat_lower: float
    yhat_upper: float
    trend: float


class ForecastResponse(ResponseSchema):
    snapshot_date: date
    horizon_days: int
    current_mtd_usd: float
    projected_month_end_usd: float
    #: None when the tenant has not set a budget. Reporting a number here that
    #: the tenant never chose is what the old hardcoded default did, and it put
    #: this response in direct contradiction with ForecastAgent's overrun
    #: recommendations, which have always read the real per-tenant budget.
    budget_usd: float | None
    over_budget: bool
    overrun_pct: float
    next_90d_usd: float
    points: list[ForecastPoint]
    actuals: list[dict[str, Any]]  # [{"ds": date, "y": float}, ...]


class BudgetUpdate(APISchema):
    """Request body for setting the tenant's monthly budget.

    Deliberately carries *only* the field that is actually persisted. The
    earlier version of this schema also accepted ``warning_threshold_pct``,
    ``danger_threshold_pct`` and ``alerts_enabled``, none of which have a
    column to be stored in — accepting them would have silently dropped what
    the caller sent, which is the API-level version of a control that looks
    functional and does nothing. ``extra='forbid'`` (from APISchema) now
    rejects them outright instead.
    """

    budget_usd: float = Field(ge=0, le=1_000_000_000)


class BudgetResponse(ResponseSchema):
    budget_usd: float | None
