"""MetricSample must be filtered by the ORM listener itself.

The last table to get a second isolation layer. Until migration 005,
``metric_samples`` carried no ``organization_id`` — it was scoped transitively
through ``resource_id -> resources.organization_id``, which the
``do_orm_execute`` listener in ``core/tenant.py`` cannot follow (it filters
entities that *declare* the column). Isolation rested entirely on callers
constraining on resource ids they had already proven in-org
(``RightSizingAgent._p95``, ``ResourceService.get_resource``). Correct, but a
single layer — the exact gap docs/security.md flagged as "still uncovered".

Like ``test_tenant_isolation_resources.py``, every test here uses a **naive
statement that does no manual scoping** — ``select(MetricSample)`` with no
``resource_id.in_(...)``. That is the point: it isolates the ORM guard from the
service-layer code that was already doing the job correctly. If the listener is
not engaging, these return the other tenant's telemetry.

Gated behind ``CLOUDPILOT_TEST_DB`` like the rest of the DB-backed suite.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cloudpilot.core.tenant import TenantContext
from cloudpilot.database import Base
from cloudpilot.models.cloud_account import CloudAccount, CloudProvider
from cloudpilot.models.metric_sample import MetricSample
from cloudpilot.models.organization import Organization
from cloudpilot.models.resource import Resource

TEST_DB_URL = os.environ.get("CLOUDPILOT_TEST_DB")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="CLOUDPILOT_TEST_DB not set; skipping DB-backed tests"
)

_TABLES = ["organizations", "cloud_accounts", "resources", "metric_samples"]

#: Samples per resource, and the metric each carries.
_SAMPLES_PER_RESOURCE = 3


@pytest.fixture
async def orgs():
    """Two organizations, each with one resource carrying three metric samples."""
    eng = create_async_engine(TEST_DB_URL, future=True, poolclass=NullPool)
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    session_factory = async_sessionmaker(bind=eng, expire_on_commit=False)
    ids: dict[str, uuid.UUID] = {}
    now = datetime.now(UTC)

    async with session_factory() as db:
        for label, cpu in (("a", 10.0), ("b", 90.0)):
            org = Organization(name=f"Org {label.upper()}")
            db.add(org)
            await db.flush()
            account = CloudAccount(
                organization_id=org.id,
                provider=CloudProvider.AZURE,
                display_name=f"{label}-azure",
                account_identifier=f"sub-{label}",
                credentials_enc="",
            )
            db.add(account)
            await db.flush()
            resource = Resource(
                organization_id=org.id,
                cloud_account_id=account.id,
                provider_resource_id=f"/rid/{label}",
                name=f"vm-{label}",
                service="virtual_machine",
                region="westeurope",
                sku="Standard_D4s_v3",
            )
            db.add(resource)
            await db.flush()
            for i in range(_SAMPLES_PER_RESOURCE):
                db.add(
                    MetricSample(
                        organization_id=org.id,
                        resource_id=resource.id,
                        metric_name="cpu_percent",
                        timestamp=now - timedelta(hours=i),
                        value=cpu,
                        unit="percent",
                    )
                )
            ids[f"org_{label}"] = org.id
            ids[f"resource_{label}"] = resource.id
        await db.commit()

    yield session_factory, ids
    await eng.dispose()


async def test_naive_select_returns_only_the_bound_tenants_samples(orgs) -> None:
    session_factory, ids = orgs
    async with session_factory() as db, TenantContext(ids["org_a"]):
        rows = (await db.execute(select(MetricSample))).scalars().all()

    assert len(rows) == _SAMPLES_PER_RESOURCE
    assert {r.organization_id for r in rows} == {ids["org_a"]}
    # Org B's samples carry a distinctive value; none may appear.
    assert all(r.value == 10.0 for r in rows)


async def test_idor_shaped_lookup_of_another_tenants_resource_returns_nothing(orgs) -> None:
    """Bound to org A, asking directly for org B's resource id by primary key."""
    session_factory, ids = orgs
    async with session_factory() as db, TenantContext(ids["org_a"]):
        rows = (
            await db.execute(
                select(MetricSample).where(MetricSample.resource_id == ids["resource_b"])
            )
        ).scalars().all()
    assert rows == []


async def test_aggregate_does_not_span_tenants(orgs) -> None:
    """A p95/avg over another tenant's telemetry would silently skew any
    right-sizing decision derived from it."""
    session_factory, ids = orgs
    async with session_factory() as db, TenantContext(ids["org_a"]):
        avg = (
            await db.execute(select(func.avg(MetricSample.value)))
        ).scalar_one()
    # Org A's samples are all 10.0; org B's are 90.0. A leak shows as 50.0.
    assert float(avg) == 10.0


async def test_join_to_resources_stays_within_the_tenant(orgs) -> None:
    session_factory, ids = orgs
    async with session_factory() as db, TenantContext(ids["org_b"]):
        rows = (
            await db.execute(
                select(MetricSample).join(Resource, Resource.id == MetricSample.resource_id)
            )
        ).scalars().all()
    assert len(rows) == _SAMPLES_PER_RESOURCE
    assert {r.organization_id for r in rows} == {ids["org_b"]}


async def test_unbound_context_sees_everything(orgs) -> None:
    """The scheduler has no request lifecycle, so nothing binds the ContextVar
    and the listener is deliberately a no-op — agents filter explicitly
    instead. Locking that in so the behaviour is a choice, not an accident.
    See tests/test_scheduler_isolation.py."""
    session_factory, _ = orgs
    async with session_factory() as db:
        rows = (await db.execute(select(MetricSample))).scalars().all()
    assert len(rows) == _SAMPLES_PER_RESOURCE * 2
