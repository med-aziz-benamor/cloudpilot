"""Resource service — inventory listing, the explorer tree, and resource detail."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount
from cloudpilot.models.metric_sample import MetricSample
from cloudpilot.models.recommendation import Recommendation, RecommendationStatus
from cloudpilot.models.resource import Resource
from cloudpilot.schemas.resource import (
    MetricPoint,
    ResourceDetailResponse,
    ResourceMetricSeries,
    ResourceResponse,
    ResourceTreeNode,
)


class ResourceService:
    def __init__(self, db: AsyncSession, organization_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = organization_id

    async def _account_map(self) -> dict[uuid.UUID, CloudAccount]:
        rows = (
            await self.db.execute(
                select(CloudAccount).where(CloudAccount.organization_id == self.org_id)
            )
        ).scalars().all()
        return {a.id: a for a in rows}

    async def _monthly_cost_by_resource(self) -> dict[uuid.UUID, float]:
        rows = (
            await self.db.execute(
                select(
                    BillingEntry.resource_id,
                    func.coalesce(func.sum(BillingEntry.cost_usd), 0),
                )
                .where(BillingEntry.resource_id.is_not(None))
                .group_by(BillingEntry.resource_id)
            )
        ).all()
        return {rid: float(cost) for rid, cost in rows if rid is not None}

    async def list_resources(
        self,
        provider: str | None = None,
        service: str | None = None,
        region: str | None = None,
    ) -> list[ResourceResponse]:
        accounts = await self._account_map()
        if not accounts:
            return []
        stmt = select(Resource).where(Resource.cloud_account_id.in_(list(accounts)))
        if service:
            stmt = stmt.where(Resource.service == service)
        if region:
            stmt = stmt.where(Resource.region == region)
        resources = (await self.db.execute(stmt)).scalars().all()
        costs = await self._monthly_cost_by_resource()

        out: list[ResourceResponse] = []
        for r in resources:
            acc = accounts[r.cloud_account_id]
            if provider and acc.provider.value != provider:
                continue
            out.append(
                ResourceResponse(
                    id=r.id,
                    provider=acc.provider,
                    provider_resource_id=r.provider_resource_id,
                    name=r.name,
                    service=r.service,
                    region=r.region,
                    sku=r.sku,
                    tags=r.tags_json or {},
                    is_active=r.is_active,
                    monthly_cost_usd=round(costs.get(r.id, 0.0), 2),
                    last_seen_at=r.last_seen_at,
                )
            )
        out.sort(key=lambda x: x.monthly_cost_usd, reverse=True)
        return out

    async def build_tree(self) -> list[ResourceTreeNode]:
        """Provider → region → service hierarchy with counts and costs."""
        resources = await self.list_resources()
        # provider -> region -> service -> (count, cost)
        tree: dict[str, dict[str, dict[str, list[float]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
        )
        for r in resources:
            cell = tree[r.provider.value][r.region][r.service]
            cell[0] += 1
            cell[1] += r.monthly_cost_usd

        nodes: list[ResourceTreeNode] = []
        for provider, regions in tree.items():
            region_nodes: list[ResourceTreeNode] = []
            p_count = p_cost = 0.0
            for region, services in regions.items():
                svc_nodes: list[ResourceTreeNode] = []
                r_count = r_cost = 0.0
                for service, (count, cost) in services.items():
                    r_count += count
                    r_cost += cost
                    svc_nodes.append(
                        ResourceTreeNode(
                            key=f"{provider}/{region}/{service}",
                            label=service.replace("_", " ").title(),
                            kind="service",
                            count=int(count),
                            monthly_cost_usd=round(cost, 2),
                        )
                    )
                p_count += r_count
                p_cost += r_cost
                region_nodes.append(
                    ResourceTreeNode(
                        key=f"{provider}/{region}",
                        label=region,
                        kind="region",
                        count=int(r_count),
                        monthly_cost_usd=round(r_cost, 2),
                        children=svc_nodes,
                    )
                )
            nodes.append(
                ResourceTreeNode(
                    key=provider,
                    label=provider.upper(),
                    kind="provider",
                    count=int(p_count),
                    monthly_cost_usd=round(p_cost, 2),
                    children=region_nodes,
                )
            )
        return nodes

    async def get_detail(self, resource_id: uuid.UUID) -> ResourceDetailResponse:
        accounts = await self._account_map()
        resource = await self.db.get(Resource, resource_id)
        if resource is None or resource.cloud_account_id not in accounts:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Resource not found.")
        acc = accounts[resource.cloud_account_id]
        costs = await self._monthly_cost_by_resource()

        # Metrics
        since = datetime.now(UTC) - timedelta(days=14)
        metric_series: list[ResourceMetricSeries] = []
        for metric in ("cpu_percent", "memory_percent"):
            rows = (
                await self.db.execute(
                    select(MetricSample.timestamp, MetricSample.value, MetricSample.unit)
                    .where(
                        MetricSample.resource_id == resource_id,
                        MetricSample.metric_name == metric,
                        MetricSample.timestamp >= since,
                    )
                    .order_by(MetricSample.timestamp)
                )
            ).all()
            if rows:
                metric_series.append(
                    ResourceMetricSeries(
                        metric_name=metric,
                        unit=rows[0][2],
                        points=[MetricPoint(timestamp=ts, value=v) for ts, v, _ in rows],
                    )
                )

        # Cost trend (30 days)
        trend_rows = (
            await self.db.execute(
                select(BillingEntry.usage_date, func.sum(BillingEntry.cost_usd))
                .where(BillingEntry.resource_id == resource_id)
                .group_by(BillingEntry.usage_date)
                .order_by(BillingEntry.usage_date)
            )
        ).all()
        cost_trend = [
            MetricPoint(
                timestamp=datetime.combine(d, datetime.min.time(), tzinfo=UTC),
                value=float(c),
            )
            for d, c in trend_rows
        ]

        rec_count = (
            await self.db.execute(
                select(func.count(Recommendation.id)).where(
                    Recommendation.organization_id == self.org_id,
                    # ARRAY.any() takes a value, but the stub types it as the
                    # relationship-level PropComparator.any() which expects a
                    # criterion. The SQL is correct; the stub is not.
                    Recommendation.affected_resource_ids.any(resource_id),  # type: ignore[arg-type]
                    Recommendation.status == RecommendationStatus.PENDING,
                )
            )
        ).scalar_one()

        return ResourceDetailResponse(
            id=resource.id,
            provider=acc.provider,
            provider_resource_id=resource.provider_resource_id,
            name=resource.name,
            service=resource.service,
            region=resource.region,
            sku=resource.sku,
            tags=resource.tags_json or {},
            is_active=resource.is_active,
            monthly_cost_usd=round(costs.get(resource.id, 0.0), 2),
            last_seen_at=resource.last_seen_at,
            metrics=metric_series,
            cost_trend=cost_trend,
            recommendation_count=int(rec_count),
        )
