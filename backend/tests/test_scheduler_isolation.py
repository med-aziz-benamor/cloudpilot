"""The scheduler processes every organization in one pass — prove it cannot cross tenants.

Context: the scheduler process has no request lifecycle, so nothing binds the
``ContextVar`` that ``core/tenant.py`` reads. The ORM tenant filter is therefore a
**no-op for every query the scheduler makes**. That is by design, not a leak: the
agents take ``organization_id`` as a parameter and filter explicitly on it (see the
audit note in the session report). These tests lock that in, because the safety net
the rest of the app leans on is genuinely absent here.

Gated behind ``CLOUDPILOT_TEST_DB`` like the rest of the DB-backed suite.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cloudpilot.ai.cost_agent import CostAgent
from cloudpilot.core.tenant import get_current_org
from cloudpilot.database import Base
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount, CloudProvider
from cloudpilot.models.organization import Organization
from cloudpilot.models.recommendation import Recommendation

TEST_DB_URL = os.environ.get("CLOUDPILOT_TEST_DB")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="CLOUDPILOT_TEST_DB not set; skipping DB-backed tests"
)

# resources is pulled in by billing_entries.resource_id, even though these tests
# never populate it.
_TABLES = [
    "organizations",
    "cloud_accounts",
    "resources",
    "billing_entries",
    "recommendations",
]


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


async def _seed_org(
    db, name: str, service: str, spike_day_offset: int
) -> tuple[uuid.UUID, uuid.UUID]:
    """One org with 60 days of flat spend and a single 5x spike."""
    org = Organization(name=name)
    db.add(org)
    await db.flush()
    account = CloudAccount(
        organization_id=org.id,
        provider=CloudProvider.AZURE,
        display_name=f"{name}-azure",
        account_identifier=f"sub-{name}",
        credentials_enc="",
    )
    db.add(account)
    await db.flush()

    today = date.today()
    for i in range(60):
        day = today - timedelta(days=i)
        cost = 100.0
        if i == spike_day_offset:
            cost = 500.0
        db.add(
            BillingEntry(
                cloud_account_id=account.id,
                usage_date=day,
                service=service,
                cost_usd=Decimal(str(cost)),
                raw_currency="USD",
                raw_amount=Decimal(str(cost)),
            )
        )
    return org.id, account.id


async def test_scheduler_pass_does_not_cross_tenants(session_factory) -> None:
    """Run CostAgent for both orgs in one pass, exactly as the orchestrator does.

    No tenant context is bound anywhere — that is the scheduler's real condition.
    Each org's recommendations must reference only its own account and its own spike.
    """
    async with session_factory() as db:
        org_a, acct_a = await _seed_org(db, "OrgA", "Kubernetes", spike_day_offset=5)
        org_b, acct_b = await _seed_org(db, "OrgB", "Database", spike_day_offset=20)
        await db.commit()

    # Sanity: the scheduler really does run with no bound org.
    assert get_current_org() is None

    agent = CostAgent()
    for org_id in (org_a, org_b):
        async with session_factory() as db:
            await agent.run(org_id, db)
            await db.commit()

    async with session_factory() as db:
        recs = (await db.execute(select(Recommendation))).scalars().all()

    by_org: dict[uuid.UUID, list[Recommendation]] = {org_a: [], org_b: []}
    for r in recs:
        by_org[r.organization_id].append(r)

    assert by_org[org_a], "CostAgent found nothing for org A — the fixture spike is too small"
    assert by_org[org_b], "CostAgent found nothing for org B"

    # Each org's findings must point only at its own cloud account...
    for r in by_org[org_a]:
        assert r.cloud_account_id == acct_a
        assert r.metadata_json["service"] == "Kubernetes"
    for r in by_org[org_b]:
        assert r.cloud_account_id == acct_b
        assert r.metadata_json["service"] == "Database"


async def test_agent_ignores_other_orgs_billing(session_factory) -> None:
    """Org B's spend must not influence org A's baseline.

    If the agent leaked, org B's 60 flat days would be folded into org A's
    statistics and shift the mean the spike is measured against.
    """
    async with session_factory() as db:
        org_a, acct_a = await _seed_org(db, "OrgA", "Kubernetes", spike_day_offset=5)
        # Org B on the SAME service name, with a wildly different cost scale.
        org_b, _ = await _seed_org(db, "OrgB", "Kubernetes", spike_day_offset=5)
        async with db.begin_nested():
            for entry in (
                await db.execute(
                    select(BillingEntry).where(
                        BillingEntry.cloud_account_id != acct_a
                    )
                )
            ).scalars():
                entry.cost_usd = Decimal("100000")
        await db.commit()

    agent = CostAgent()
    async with session_factory() as db:
        await agent.run(org_a, db)
        await db.commit()

    async with session_factory() as db:
        recs = (
            await db.execute(
                select(Recommendation).where(Recommendation.organization_id == org_a)
            )
        ).scalars().all()

    assert recs, "expected org A's own spike to be detected"
    for r in recs:
        # Baseline must be org A's ~100/day, not contaminated by org B's 100000/day.
        assert r.metadata_json["expected_cost"] < 200, (
            f"org A's baseline was polluted by another tenant: {r.metadata_json}"
        )
        assert r.cloud_account_id == acct_a


async def test_agent_creates_nothing_for_org_without_accounts(session_factory) -> None:
    """An org with no cloud accounts must not inherit anyone else's findings."""
    async with session_factory() as db:
        org_a, _ = await _seed_org(db, "OrgA", "Kubernetes", spike_day_offset=5)
        empty = Organization(name="Empty")
        db.add(empty)
        await db.flush()
        empty_id = empty.id
        await db.commit()

    agent = CostAgent()
    for org_id in (org_a, empty_id):
        async with session_factory() as db:
            await agent.run(org_id, db)
            await db.commit()

    async with session_factory() as db:
        recs = (
            await db.execute(
                select(Recommendation).where(Recommendation.organization_id == empty_id)
            )
        ).scalars().all()
    assert recs == []
