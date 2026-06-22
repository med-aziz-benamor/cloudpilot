"""RightSizingAgent — over-provisioned resource detection.

Algorithm:
1. Load active resources with a SKU (VMs, node pools, databases).
2. For each, compute P95 CPU% and P95 memory% over 14 days of metric_samples.
3. If P95(CPU) < 40% AND P95(mem) < 60% → downsize candidate.
4. Look up the next-smaller SKU in the pricing catalog and compute the saving.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.ai.base_agent import AgentBase
from cloudpilot.ai.pricing import next_smaller_sku, sku_hourly_price
from cloudpilot.models.cloud_account import CloudAccount
from cloudpilot.models.metric_sample import MetricSample
from cloudpilot.models.recommendation import (
    AgentType,
    Recommendation,
    RecommendationStatus,
)
from cloudpilot.models.resource import Resource

_METRIC_DAYS = 14
_CPU_THRESHOLD = 40.0
_MEM_THRESHOLD = 60.0
_HOURS_PER_MONTH = 730


class RightSizingAgent(AgentBase):
    name = "RightSizingAgent"
    description = "Identifies over-provisioned resources (P95 CPU/RAM below target)."
    agent_type = AgentType.RIGHTSIZING

    async def run(self, organization_id: uuid.UUID, db: AsyncSession) -> int:
        account_ids = (
            (await db.execute(
                select(CloudAccount.id).where(
                    CloudAccount.organization_id == organization_id
                )
            )).scalars().all()
        )
        if not account_ids:
            return 0

        resources = (
            (await db.execute(
                select(Resource).where(
                    Resource.cloud_account_id.in_(account_ids),
                    Resource.is_active.is_(True),
                    Resource.sku.is_not(None),
                )
            )).scalars().all()
        )

        existing = await self._existing_resource_ids(db, organization_id)
        since = datetime.now(timezone.utc) - timedelta(days=_METRIC_DAYS)
        created = 0

        for res in resources:
            if res.id in existing:
                continue
            p95_cpu = await self._p95(db, res.id, "cpu_percent", since)
            p95_mem = await self._p95(db, res.id, "memory_percent", since)
            if p95_cpu is None or p95_mem is None:
                continue
            if not (p95_cpu < _CPU_THRESHOLD and p95_mem < _MEM_THRESHOLD):
                continue

            target_sku = next_smaller_sku(res.sku)
            if target_sku is None:
                continue
            current_price = sku_hourly_price(res.sku)
            target_price = sku_hourly_price(target_sku)
            saving = max(0.0, (current_price - target_price) * _HOURS_PER_MONTH)
            if saving <= 0:
                continue

            bonus = (_CPU_THRESHOLD - p95_cpu) / _CPU_THRESHOLD * 0.2
            confidence = min(0.92, 0.7 + max(0.0, bonus))

            rec = Recommendation(
                organization_id=organization_id,
                cloud_account_id=res.cloud_account_id,
                agent=AgentType.RIGHTSIZING,
                title=f"Underutilized resource — {res.name}",
                description=(
                    f"{res.sku} running at P95 CPU {p95_cpu:.0f}%, P95 RAM "
                    f"{p95_mem:.0f}%. Recommend downsizing to {target_sku}."
                ),
                estimated_saving_usd=Decimal(str(round(saving, 2))),
                confidence=round(confidence, 2),
                status=RecommendationStatus.PENDING,
                affected_resource_ids=[res.id],
                metadata_json={
                    "current_sku": res.sku,
                    "target_sku": target_sku,
                    "p95_cpu": round(p95_cpu, 1),
                    "p95_mem": round(p95_mem, 1),
                    "current_price_usd_hr": round(current_price, 4),
                    "target_price_usd_hr": round(target_price, 4),
                },
            )
            db.add(rec)
            created += 1

        await db.flush()
        logger.info(
            "RightSizingAgent created {} recommendations for org {}", created, organization_id
        )
        return created

    async def _p95(
        self, db: AsyncSession, resource_id: uuid.UUID, metric: str, since: datetime
    ) -> float | None:
        rows = (
            (await db.execute(
                select(MetricSample.value).where(
                    MetricSample.resource_id == resource_id,
                    MetricSample.metric_name == metric,
                    MetricSample.timestamp >= since,
                )
            )).scalars().all()
        )
        if not rows:
            return None
        return float(np.percentile(np.array(rows, dtype=float), 95))

    async def _existing_resource_ids(
        self, db: AsyncSession, organization_id: uuid.UUID
    ) -> set[uuid.UUID]:
        rows = (
            (await db.execute(
                select(Recommendation).where(
                    Recommendation.organization_id == organization_id,
                    Recommendation.agent == AgentType.RIGHTSIZING,
                    Recommendation.status.in_(
                        [RecommendationStatus.PENDING, RecommendationStatus.ACCEPTED]
                    ),
                )
            )).scalars().all()
        )
        out: set[uuid.UUID] = set()
        for r in rows:
            out.update(r.affected_resource_ids or [])
        return out
