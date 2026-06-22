"""Forecast schemas."""

from __future__ import annotations

from datetime import date

from cloudpilot.schemas.common import ResponseSchema


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
    budget_usd: float
    over_budget: bool
    overrun_pct: float
    next_90d_usd: float
    points: list[ForecastPoint]
    actuals: list[dict]  # [{"ds": date, "y": float}, ...]


class BudgetUpdate(ResponseSchema):
    budget_usd: float
    warning_threshold_pct: int = 80
    danger_threshold_pct: int = 100
    alerts_enabled: bool = True
