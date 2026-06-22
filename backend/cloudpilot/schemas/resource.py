"""Resource schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from cloudpilot.models.cloud_account import CloudProvider
from cloudpilot.schemas.common import ResponseSchema


class MetricPoint(ResponseSchema):
    timestamp: datetime
    value: float


class ResourceMetricSeries(ResponseSchema):
    metric_name: str
    unit: str
    points: list[MetricPoint]


class ResourceResponse(ResponseSchema):
    id: uuid.UUID
    provider: CloudProvider
    provider_resource_id: str
    name: str
    service: str
    region: str
    sku: str | None = None
    tags: dict[str, Any] = {}
    is_active: bool
    monthly_cost_usd: float = 0.0
    last_seen_at: datetime | None = None


class ResourceDetailResponse(ResourceResponse):
    metrics: list[ResourceMetricSeries] = []
    cost_trend: list[MetricPoint] = []
    recommendation_count: int = 0


class ResourceTreeNode(ResponseSchema):
    """A node in the provider → region → service hierarchy used by the explorer."""

    key: str
    label: str
    kind: str  # 'provider' | 'region' | 'service'
    count: int
    monthly_cost_usd: float
    children: list["ResourceTreeNode"] = []


ResourceTreeNode.model_rebuild()
