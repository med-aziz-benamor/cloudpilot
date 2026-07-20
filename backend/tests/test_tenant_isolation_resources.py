"""Resource and BillingEntry must be filtered by the ORM listener itself.

Until migration 004 these two tables carried no ``organization_id``. They were scoped
transitively through ``cloud_account_id``, which the ``do_orm_execute`` listener in
``core/tenant.py`` cannot follow — it filters entities that *declare* the column. So
the platform's two largest tables were protected by one layer only: services
remembering to resolve ``account_ids`` first. Correct, but not defence in depth.

Every test here queries with a **naive statement that does no manual scoping** —
``select(Resource)``, no ``cloud_account_id.in_(...)``. That is the whole point: it
isolates the ORM guard from the service-layer code that was already doing the job. If
the listener is not engaging, these return the other tenant's rows.

Gated behind ``CLOUDPILOT_TEST_DB`` like the rest of the DB-backed suite.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cloudpilot.core.tenant import TenantContext
from cloudpilot.database import Base
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount, CloudProvider
from cloudpilot.models.organization import Organization
from cloudpilot.models.resource import Resource

TEST_DB_URL = os.environ.get("CLOUDPILOT_TEST_DB")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="CLOUDPILOT_TEST_DB not set; skipping DB-backed tests"
)

_TABLES = ["organizations", "cloud_accounts", "resources", "billing_entries"]


@pytest.fixture
async def orgs():
    """Two organizations, each with a cloud account, a resource and two billing rows."""
    eng = create_async_engine(TEST_DB_URL, future=True, poolclass=NullPool)
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all, tables=tables)

    session_factory = async_sessionmaker(bind=eng, expire_on_commit=False)
    ids: dict[str, uuid.UUID] = {}
    async with session_factory() as db:
        for label in ("a", "b"):
            org = Organization(name=f"Org {label.upper()}")
            db.add(org)
            await db.flush()
            ids[f"org_{label}"] = org.id

            account = CloudAccount(
                organization_id=org.id,
                provider=CloudProvider.AZURE,
                display_name=f"{label}-azure",
                account_identifier=f"sub-{label}",
                credentials_enc="",
            )
            db.add(account)
            await db.flush()
            ids[f"account_{label}"] = account.id

            resource = Resource(
                organization_id=org.id,
                cloud_account_id=account.id,
                provider_resource_id=f"/rid/{label}",
                name=f"vm-{label}",
                service="virtual_machine",
                region="westeurope",
                sku="Standard_D4s_v3",
                node_count=1,
                is_active=True,
                last_seen_at=datetime.now(UTC),
            )
            db.add(resource)
            await db.flush()
            ids[f"resource_{label}"] = resource.id

            for offset in range(2):
                db.add(
                    BillingEntry(
                        organization_id=org.id,
                        cloud_account_id=account.id,
                        resource_id=resource.id,
                        usage_date=date(2026, 7, 1 + offset),
                        service="Virtual Machines",
                        cost_usd=Decimal("10.00"),
                        raw_currency="USD",
                        raw_amount=Decimal("10.00"),
                    )
                )
        await db.commit()
    yield ids, session_factory
    await eng.dispose()


# ── Resource ────────────────────────────────────────────────────────────────


async def test_naive_resource_query_is_scoped(orgs) -> None:
    """``select(Resource)`` with no manual scoping must return only org A's rows."""
    ids, session_factory = orgs
    async with session_factory() as db, TenantContext(ids["org_a"]):
        rows = (await db.execute(select(Resource))).scalars().all()

    assert [r.id for r in rows] == [ids["resource_a"]]
    assert all(r.organization_id == ids["org_a"] for r in rows)


async def test_naive_resource_query_scoped_for_other_org(orgs) -> None:
    """Symmetric: binding org B sees only B, so the test is not passing by luck."""
    ids, session_factory = orgs
    async with session_factory() as db, TenantContext(ids["org_b"]):
        rows = (await db.execute(select(Resource))).scalars().all()

    assert [r.id for r in rows] == [ids["resource_b"]]


async def test_resource_get_by_id_across_tenants_returns_nothing(orgs) -> None:
    """Asking for another tenant's resource by primary key must not find it.

    This is the IDOR shape: the caller already knows the id.
    """
    ids, session_factory = orgs
    async with session_factory() as db, TenantContext(ids["org_a"]):
        row = (
            await db.execute(
                select(Resource).where(Resource.id == ids["resource_b"])
            )
        ).scalar_one_or_none()

    assert row is None


async def test_resource_aggregate_is_scoped(orgs) -> None:
    """A COUNT must not leak the other tenant's row count."""
    ids, session_factory = orgs
    async with session_factory() as db, TenantContext(ids["org_a"]):
        total = (await db.execute(select(func.count(Resource.id)))).scalar_one()
    assert total == 1


# ── BillingEntry ────────────────────────────────────────────────────────────


async def test_naive_billing_query_is_scoped(orgs) -> None:
    """``select(BillingEntry)`` with no manual scoping must return only org A's rows."""
    ids, session_factory = orgs
    async with session_factory() as db, TenantContext(ids["org_a"]):
        rows = (await db.execute(select(BillingEntry))).scalars().all()

    assert len(rows) == 2
    assert all(r.organization_id == ids["org_a"] for r in rows)


async def test_billing_sum_is_scoped(orgs) -> None:
    """The number that drives every cost KPI must not include another tenant's spend.

    Both orgs have $20; an unfiltered SUM would report $40.
    """
    ids, session_factory = orgs
    async with session_factory() as db, TenantContext(ids["org_a"]):
        total = (
            await db.execute(select(func.coalesce(func.sum(BillingEntry.cost_usd), 0)))
        ).scalar_one()

    assert float(total) == 20.0, f"expected only org A's spend, got {total}"


# ── Both together, and the no-context escape hatch ──────────────────────────


async def test_resource_billing_join_is_scoped_on_both_sides(orgs) -> None:
    """The two tables joined: neither side may contribute another tenant's rows.

    This is the join the brief originally cited. It only became a *tenant-listener*
    concern once both tables carried the column — before migration 004 neither side
    was filtered by the listener at all.
    """
    ids, session_factory = orgs
    stmt = select(Resource, BillingEntry).join(
        BillingEntry, BillingEntry.resource_id == Resource.id
    )
    async with session_factory() as db, TenantContext(ids["org_a"]):
        rows = (await db.execute(stmt)).all()

    assert rows
    for resource, entry in rows:
        assert resource.organization_id == ids["org_a"]
        assert entry.organization_id == ids["org_a"]


async def test_uncorrelated_two_table_select_is_scoped(orgs) -> None:
    """A cartesian select — the shape that exposed the old ``break`` bug."""
    ids, session_factory = orgs
    async with session_factory() as db, TenantContext(ids["org_b"]):
        rows = (await db.execute(select(Resource, BillingEntry))).all()

    assert rows
    for resource, entry in rows:
        assert resource.organization_id == ids["org_b"]
        assert entry.organization_id == ids["org_b"]


async def test_no_context_sees_everything(orgs) -> None:
    """Unbound context still spans tenants — the seeder and scheduler rely on this."""
    _ids, session_factory = orgs
    async with session_factory() as db:
        resources = (await db.execute(select(Resource))).scalars().all()
        billing = (await db.execute(select(BillingEntry))).scalars().all()

    assert len(resources) == 2
    assert len(billing) == 4
