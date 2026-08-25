"""Cost service — summary KPIs, breakdowns, timeseries, top drivers, anomalies."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.config import settings
from cloudpilot.core import cache
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount, CloudProvider
from cloudpilot.models.recommendation import (
    AgentType,
    Recommendation,
    RecommendationStatus,
)
from cloudpilot.models.resource import Resource
from cloudpilot.schemas.cost import (
    AnomalyEntry,
    CostSummary,
    CostTimeseriesPoint,
    CostTimeseriesResponse,
    ProviderCost,
    ServiceCost,
    TopCostDriver,
)


class CostService:
    def __init__(self, db: AsyncSession, organization_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = organization_id

    async def _accounts(self) -> dict[uuid.UUID, CloudAccount]:
        rows = (
            await self.db.execute(
                select(CloudAccount).where(CloudAccount.organization_id == self.org_id)
            )
        ).scalars().all()
        return {a.id: a for a in rows}

    async def get_summary(self) -> CostSummary:
        key = cache.org_key(self.org_id, "summary")
        if (hit := await cache.get_json(key)) is not None:
            return CostSummary.model_validate(hit)
        summary = await self._compute_summary()
        await cache.set_json(key, summary.model_dump(mode="json"), settings.CACHE_DASHBOARD_TTL)
        return summary

    async def _compute_summary(self) -> CostSummary:
        accounts = await self._accounts()
        if not accounts:
            return CostSummary(
                mtd_usd=0, projected_month_end_usd=0, last_month_usd=0, delta_pct=0,
                potential_savings_usd=0, optimization_score=100, connected_clouds=0,
                pending_recommendations=0,
            )
        account_ids = list(accounts)
        today = date.today()
        month_start = today.replace(day=1)

        mtd = await self._sum_between(account_ids, month_start, today)
        days_elapsed = max(1, (today - month_start).days + 1)
        days_in_month = self._days_in_month(today)
        projected = mtd / days_elapsed * days_in_month

        last_month_end = month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        last_same_point = min(
            last_month_end, last_month_start + timedelta(days=days_elapsed - 1)
        )
        last_mtd = await self._sum_between(account_ids, last_month_start, last_same_point)
        last_full = await self._sum_between(account_ids, last_month_start, last_month_end)
        delta_pct = ((mtd - last_mtd) / last_mtd * 100) if last_mtd > 0 else 0.0

        # Potential savings = sum of pending recommendation savings.
        savings = (
            await self.db.execute(
                select(func.coalesce(func.sum(Recommendation.estimated_saving_usd), 0)).where(
                    Recommendation.organization_id == self.org_id,
                    Recommendation.status == RecommendationStatus.PENDING,
                )
            )
        ).scalar_one()
        pending = (
            await self.db.execute(
                select(func.count(Recommendation.id)).where(
                    Recommendation.organization_id == self.org_id,
                    Recommendation.status == RecommendationStatus.PENDING,
                )
            )
        ).scalar_one()

        # COALESCE(..., 0) means the driver never returns NULL here, but the
        # column is nullable so the static type is Decimal | None.
        savings_usd = float(savings or 0)
        score = self._optimization_score(mtd, savings_usd)
        return CostSummary(
            mtd_usd=round(mtd, 2),
            projected_month_end_usd=round(projected, 2),
            last_month_usd=round(last_full, 2),
            delta_pct=round(delta_pct, 1),
            potential_savings_usd=round(savings_usd, 2),
            optimization_score=score,
            connected_clouds=len({a.provider for a in accounts.values()}),
            pending_recommendations=int(pending),
        )

    async def get_breakdown(self) -> dict[str, Any]:
        key = cache.org_key(self.org_id, "breakdown")
        if (hit := await cache.get_json(key)) is not None:
            return hit  # type: ignore[no-any-return]
        breakdown = await self._compute_breakdown()
        await cache.set_json(key, breakdown, settings.CACHE_DASHBOARD_TTL)
        return breakdown

    async def _compute_breakdown(self) -> dict[str, Any]:
        accounts = await self._accounts()
        account_ids = list(accounts)
        if not account_ids:
            return {"by_provider": [], "by_service": [], "by_region": []}

        today = date.today()
        month_start = today.replace(day=1)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)

        # Region lives on the resource, not the billing row, so join through it. A
        # billing row with no resource (rare) is bucketed as "unassigned" rather than
        # dropped, so the region totals still sum to the provider totals.
        region_by_resource: dict[uuid.UUID, str] = {
            row.id: row.region
            for row in (
                await self.db.execute(
                    select(Resource.id, Resource.region).where(
                        Resource.cloud_account_id.in_(account_ids)
                    )
                )
            ).all()
        }

        rows = (
            await self.db.execute(
                select(
                    BillingEntry.cloud_account_id,
                    BillingEntry.service,
                    BillingEntry.usage_date,
                    BillingEntry.cost_usd,
                    BillingEntry.resource_id,
                ).where(
                    BillingEntry.cloud_account_id.in_(account_ids),
                    BillingEntry.usage_date >= last_month_start,
                )
            )
        ).all()

        prov_total: dict[CloudProvider, float] = defaultdict(float)
        svc_mtd: dict[tuple[str, CloudProvider], float] = defaultdict(float)
        svc_last: dict[tuple[str, CloudProvider], float] = defaultdict(float)
        region_total: dict[str, float] = defaultdict(float)

        for acc_id, service, usage_date, cost, resource_id in rows:
            provider = accounts[acc_id].provider
            c = float(cost)
            if usage_date >= month_start:
                prov_total[provider] += c
                svc_mtd[(service, provider)] += c
                region_total[region_by_resource.get(resource_id) or "unassigned"] += c
            else:
                svc_last[(service, provider)] += c

        total_mtd = sum(prov_total.values()) or 1.0
        by_provider = [
            ProviderCost(
                provider=p, cost_usd=round(v, 2), pct_of_total=round(v / total_mtd * 100, 1)
            )
            for p, v in sorted(prov_total.items(), key=lambda x: x[1], reverse=True)
        ]
        by_service = [
            ServiceCost(
                service=svc,
                provider=prov,
                cost_usd=round(v, 2),
                vs_last_month_pct=round(
                    (v - svc_last.get((svc, prov), 0))
                    / svc_last.get((svc, prov), 1)
                    * 100,
                    1,
                )
                if svc_last.get((svc, prov), 0) > 0
                else 0.0,
                pct_of_total=round(v / total_mtd * 100, 1),
            )
            for (svc, prov), v in sorted(svc_mtd.items(), key=lambda x: x[1], reverse=True)
        ][:15]

        by_region = [
            {"region": region, "cost_usd": round(v, 2)}
            for region, v in sorted(region_total.items(), key=lambda x: x[1], reverse=True)
        ]
        return {"by_provider": by_provider, "by_service": by_service, "by_region": by_region}

    async def get_timeseries(self, period_days: int = 90) -> CostTimeseriesResponse:
        # The period is part of the key: the 7/30/90-day views are different
        # answers to different questions and must not share an entry.
        key = cache.org_key(self.org_id, "timeseries", period_days)
        if (hit := await cache.get_json(key)) is not None:
            return CostTimeseriesResponse.model_validate(hit)
        series = await self._compute_timeseries(period_days)
        await cache.set_json(key, series.model_dump(mode="json"), settings.CACHE_DASHBOARD_TTL)
        return series

    async def _compute_timeseries(self, period_days: int = 90) -> CostTimeseriesResponse:
        accounts = await self._accounts()
        account_ids = list(accounts)
        if not account_ids:
            return CostTimeseriesResponse(period_days=period_days, points=[])
        since = date.today() - timedelta(days=period_days)
        rows = (
            await self.db.execute(
                select(
                    BillingEntry.usage_date,
                    BillingEntry.cloud_account_id,
                    func.sum(BillingEntry.cost_usd),
                )
                .where(
                    BillingEntry.cloud_account_id.in_(account_ids),
                    BillingEntry.usage_date >= since,
                )
                .group_by(BillingEntry.usage_date, BillingEntry.cloud_account_id)
                .order_by(BillingEntry.usage_date)
            )
        ).all()

        per_day: dict[date, dict[str, float]] = defaultdict(
            lambda: {"azure": 0.0, "aws": 0.0, "gcp": 0.0}
        )
        for usage_date, acc_id, cost in rows:
            provider = accounts[acc_id].provider.value
            per_day[usage_date][provider] += float(cost)

        points = [
            CostTimeseriesPoint(
                usage_date=d,
                azure=round(v["azure"], 2),
                aws=round(v["aws"], 2),
                gcp=round(v["gcp"], 2),
                total=round(v["azure"] + v["aws"] + v["gcp"], 2),
            )
            for d, v in sorted(per_day.items())
        ]
        return CostTimeseriesResponse(period_days=period_days, points=points)

    async def get_top_drivers(self, limit: int = 5) -> list[TopCostDriver]:
        accounts = await self._accounts()
        account_ids = list(accounts)
        if not account_ids:
            return []
        rows = (
            await self.db.execute(
                select(
                    BillingEntry.resource_id, func.sum(BillingEntry.cost_usd)
                )
                .where(
                    BillingEntry.cloud_account_id.in_(account_ids),
                    BillingEntry.resource_id.is_not(None),
                )
                .group_by(BillingEntry.resource_id)
                .order_by(func.sum(BillingEntry.cost_usd).desc())
                .limit(limit)
            )
        ).all()
        out: list[TopCostDriver] = []
        for rid, cost in rows:
            resource = await self.db.get(Resource, rid)
            if not resource:
                continue
            acc = accounts[resource.cloud_account_id]
            out.append(
                TopCostDriver(
                    resource_id=str(rid),
                    name=resource.name,
                    provider=acc.provider,
                    service=resource.service,
                    monthly_cost_usd=round(float(cost), 2),
                    trend=await self._resource_trend(rid),
                )
            )
        return out

    async def get_anomalies(self) -> list[AnomalyEntry]:
        recs = (
            await self.db.execute(
                select(Recommendation).where(
                    Recommendation.organization_id == self.org_id,
                    Recommendation.agent == AgentType.COST,
                )
            )
        ).scalars().all()
        out: list[AnomalyEntry] = []
        for r in recs:
            md = r.metadata_json or {}
            if not md.get("anomaly_date"):
                continue
            out.append(
                AnomalyEntry(
                    usage_date=date.fromisoformat(md["anomaly_date"]),
                    provider=CloudProvider(md.get("provider", "azure")),
                    service=md.get("service", "unknown"),
                    expected_usd=float(md.get("expected_cost", 0)),
                    actual_usd=float(md.get("actual_cost", 0)),
                    delta_usd=float(md.get("delta_usd", 0)),
                    delta_pct=round(
                        (md.get("actual_cost", 0) - md.get("expected_cost", 0))
                        / (md.get("expected_cost", 1) or 1)
                        * 100,
                        1,
                    ),
                )
            )
        out.sort(key=lambda x: x.usage_date, reverse=True)
        return out

    # ─── helpers ───
    async def _sum_between(
        self, account_ids: list[uuid.UUID], start: date, end: date
    ) -> float:
        total = (
            await self.db.execute(
                select(func.coalesce(func.sum(BillingEntry.cost_usd), 0)).where(
                    BillingEntry.cloud_account_id.in_(account_ids),
                    BillingEntry.usage_date >= start,
                    BillingEntry.usage_date <= end,
                )
            )
        ).scalar_one()
        return float(total)

    async def _resource_trend(self, resource_id: uuid.UUID) -> list[float]:
        since = date.today() - timedelta(days=7)
        rows = (
            await self.db.execute(
                select(BillingEntry.usage_date, func.sum(BillingEntry.cost_usd))
                .where(
                    BillingEntry.resource_id == resource_id,
                    BillingEntry.usage_date >= since,
                )
                .group_by(BillingEntry.usage_date)
                .order_by(BillingEntry.usage_date)
            )
        ).all()
        return [round(float(c), 2) for _, c in rows]

    @staticmethod
    def _days_in_month(d: date) -> int:
        if d.month == 12:
            return 31
        return (date(d.year, d.month + 1, 1) - timedelta(days=1)).day

    @staticmethod
    def _optimization_score(mtd: float, savings: float) -> int:
        """0–100 health score: higher when waste (savings as % of spend) is lower."""
        if mtd <= 0:
            return 100
        waste_ratio = min(1.0, savings / mtd)
        return max(0, min(100, round(100 - waste_ratio * 100)))
