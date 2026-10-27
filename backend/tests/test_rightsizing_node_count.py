"""RightSizingAgent must price a downsize per node, not per resource.

Migration 002 added ``resources.node_count`` to fix exactly this: a 3-node AKS pool
was quoting the saving of downsizing a *single* node, under-reporting by 3x. These
tests pin the multiplication down so the column cannot quietly stop being applied.

Gated behind ``CLOUDPILOT_TEST_DB`` — the saving is computed inline in
``RightSizingAgent.run``, so exercising it needs a real row, not a pure function.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cloudpilot.ai.pricing import next_smaller_sku, sku_hourly_price
from cloudpilot.ai.rightsizing_agent import RightSizingAgent
from cloudpilot.database import Base
from cloudpilot.models.cloud_account import CloudAccount, CloudProvider
from cloudpilot.models.metric_sample import MetricSample
from cloudpilot.models.organization import Organization
from cloudpilot.models.recommendation import Recommendation
from cloudpilot.models.resource import Resource

TEST_DB_URL = os.environ.get("CLOUDPILOT_TEST_DB")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="CLOUDPILOT_TEST_DB not set; skipping DB-backed tests"
)

_TABLES = [
    "organizations",
    "cloud_accounts",
    "resources",
    "metric_samples",
    "recommendations",
]

_SKU = "Standard_D4s_v3"
_HOURS_PER_MONTH = 730


@pytest.fixture
async def session_factory():
    eng = create_async_engine(TEST_DB_URL, future=True, poolclass=NullPool)
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        # Drop the whole schema, not just our subset: the DB-backed test files share
        # one database, and a table left by another file can hold an FK onto ours.
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    yield async_sessionmaker(bind=eng, expire_on_commit=False)
    await eng.dispose()


async def _seed_idle_resource(db, node_count: int) -> uuid.UUID:
    """One resource, idle enough to trigger a downsize, with ``node_count`` nodes."""
    org = Organization(name=f"Org-{node_count}")
    db.add(org)
    await db.flush()
    account = CloudAccount(
        organization_id=org.id,
        provider=CloudProvider.AZURE,
        display_name="az",
        account_identifier=f"sub-{node_count}",
        credentials_enc="",
    )
    db.add(account)
    await db.flush()
    resource = Resource(
        organization_id=org.id,
        cloud_account_id=account.id,
        provider_resource_id=f"/rid/{node_count}",
        name=f"pool-{node_count}",
        service="kubernetes",
        region="westeurope",
        sku=_SKU,
        node_count=node_count,
        is_active=True,
    )
    db.add(resource)
    await db.flush()

    # Well under the 40% CPU / 60% RAM thresholds so the downsize always fires.
    now = datetime.now(UTC)
    for hour in range(48):
        ts = now - timedelta(hours=hour)
        db.add(MetricSample(
            organization_id=org.id, resource_id=resource.id, metric_name="cpu_percent",
            timestamp=ts, value=8.0, unit="percent",
        ))
        db.add(MetricSample(
            organization_id=org.id, resource_id=resource.id, metric_name="memory_percent",
            timestamp=ts, value=15.0, unit="percent",
        ))
    return org.id


async def _saving_for(session_factory, node_count: int) -> float:
    async with session_factory() as db:
        org_id = await _seed_idle_resource(db, node_count)
        await db.commit()
    async with session_factory() as db:
        await RightSizingAgent().run(org_id, db)
        await db.commit()
    async with session_factory() as db:
        recs = (
            await db.execute(
                select(Recommendation).where(Recommendation.organization_id == org_id)
            )
        ).scalars().all()
    assert len(recs) == 1, f"expected exactly one downsize recommendation, got {len(recs)}"
    # The agent clamps with max(1, ...), so 0 is recorded as 1.
    assert recs[0].metadata_json["node_count"] == max(1, node_count)
    return float(recs[0].estimated_saving_usd)


async def test_single_node_saving_is_one_node_delta(session_factory) -> None:
    saving = await _saving_for(session_factory, 1)
    expected = (
        sku_hourly_price(_SKU) - sku_hourly_price(next_smaller_sku(_SKU))
    ) * _HOURS_PER_MONTH
    assert saving == pytest.approx(expected, rel=1e-3)


async def test_three_node_pool_prices_three_node_delta(session_factory) -> None:
    """The regression: a 3-node pool must quote 3x the per-node delta, not 1x."""
    saving = await _saving_for(session_factory, 3)
    per_node = (
        sku_hourly_price(_SKU) - sku_hourly_price(next_smaller_sku(_SKU))
    ) * _HOURS_PER_MONTH
    assert saving == pytest.approx(per_node * 3, rel=1e-3)
    # Stated explicitly, because this is the exact bug migration 002 fixed.
    assert saving > per_node, "3-node pool priced as a single node"


async def test_saving_scales_linearly_with_node_count(session_factory) -> None:
    one = await _saving_for(session_factory, 1)
    four = await _saving_for(session_factory, 4)
    assert four == pytest.approx(one * 4, rel=1e-3)


async def test_zero_node_count_is_treated_as_one(session_factory) -> None:
    """``max(1, node_count)`` guards a bad sync writing 0; the saving must not vanish."""
    saving = await _saving_for(session_factory, 0)
    expected = (
        sku_hourly_price(_SKU) - sku_hourly_price(next_smaller_sku(_SKU))
    ) * _HOURS_PER_MONTH
    assert saving == pytest.approx(expected, rel=1e-3)
