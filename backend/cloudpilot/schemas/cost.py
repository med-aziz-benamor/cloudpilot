"""Cost analytics schemas."""

from __future__ import annotations

from datetime import date

from cloudpilot.models.cloud_account import CloudProvider
from cloudpilot.schemas.common import ResponseSchema


class CostSummary(ResponseSchema):
    """Headline figures for the overview KPIs."""

    mtd_usd: float
    projected_month_end_usd: float
    last_month_usd: float
    delta_pct: float  # MTD vs same point last month
    potential_savings_usd: float
    optimization_score: int  # 0–100
    connected_clouds: int
    pending_recommendations: int


class ProviderCost(ResponseSchema):
    provider: CloudProvider
    cost_usd: float
    pct_of_total: float


class ServiceCost(ResponseSchema):
    service: str
    provider: CloudProvider
    cost_usd: float
    vs_last_month_pct: float
    pct_of_total: float


class CostTimeseriesPoint(ResponseSchema):
    usage_date: date
    azure: float
    aws: float
    gcp: float
    total: float


class CostBreakdownResponse(ResponseSchema):
    by_provider: list[ProviderCost]
    by_service: list[ServiceCost]
    by_region: list[dict]


class CostTimeseriesResponse(ResponseSchema):
    period_days: int
    points: list[CostTimeseriesPoint]


class TopCostDriver(ResponseSchema):
    resource_id: str
    name: str
    provider: CloudProvider
    service: str
    monthly_cost_usd: float
    trend: list[float]


class AnomalyEntry(ResponseSchema):
    usage_date: date
    provider: CloudProvider
    service: str
    expected_usd: float
    actual_usd: float
    delta_usd: float
    delta_pct: float
