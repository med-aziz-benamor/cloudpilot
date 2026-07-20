"""Integration tests proving one tenant can never read another's rows.

These need a live Postgres (the models use ``UUID``/``JSONB``), so they are gated
behind ``CLOUDPILOT_TEST_DB`` like the rest of the DB-backed suite::

    CLOUDPILOT_TEST_DB=postgresql+asyncpg://cp:cp@localhost:5432/cloudpilot_test \
        pytest tests/test_tenant_isolation.py

The case that matters is a query touching **two** org-scoped entities at once. The
listener in ``core/tenant.py`` used to ``break`` after the first mapper carrying
``organization_id``, so the second entity in a join came back unfiltered.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cloudpilot.core.tenant import TenantContext
from cloudpilot.database import Base
from cloudpilot.models.cloud_account import CloudAccount, CloudProvider
from cloudpilot.models.organization import Organization
from cloudpilot.models.recommendation import (
    AgentType,
    Recommendation,
    RecommendationStatus,
)

TEST_DB_URL = os.environ.get("CLOUDPILOT_TEST_DB")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="CLOUDPILOT_TEST_DB not set; skipping DB-backed tests"
)


@pytest.fixture
async def engine():
    # Function-scoped with NullPool: pytest-asyncio gives each test its own event
    # loop, and a pooled connection created on a previous loop cannot be reused.
    eng = create_async_engine(TEST_DB_URL, future=True, poolclass=NullPool)
    async with eng.begin() as conn:
        tables = [
            Organization.__table__,
            CloudAccount.__table__,
            Recommendation.__table__,
        ]
        # Drop the whole schema, not just our subset: the DB-backed test files share
        # one database, and a table left by another file can hold an FK onto ours.
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    yield eng
    await eng.dispose()


@pytest.fixture
async def orgs(engine):
    """Two organizations, each with one cloud account and one recommendation."""
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
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

            rec = Recommendation(
                organization_id=org.id,
                cloud_account_id=account.id,
                agent=AgentType.RIGHTSIZING,
                title=f"{label} recommendation",
                description="test",
                status=RecommendationStatus.PENDING,
                estimated_saving_usd=10,
                confidence=0.9,
                created_at=datetime.now(UTC),
            )
            db.add(rec)
        await db.commit()
    yield ids, session_factory


async def test_single_entity_query_is_scoped(orgs) -> None:
    """Baseline: the listener already handled a single org-scoped entity."""
    ids, session_factory = orgs
    async with session_factory() as db, TenantContext(ids["org_a"]):
        rows = (await db.execute(select(Recommendation))).scalars().all()
    assert [r.organization_id for r in rows] == [ids["org_a"]]


async def test_second_org_scoped_entity_is_also_filtered(orgs) -> None:
    """The regression: EVERY org-scoped entity in the statement must be filtered.

    The listener used to ``break`` after the first mapper carrying
    ``organization_id``, leaving every later one unfiltered. Under org A this
    returned org A's recommendation paired with **org B's cloud account**.

    A two-entity select is the minimal shape that isolates this. Note that an
    FK-correlated join (``Recommendation.cloud_account_id == CloudAccount.id``)
    happens to mask the bug — filtering one side transitively constrains the
    other — which is why the flaw survived: the common query shapes hide it.
    """
    ids, session_factory = orgs
    stmt = select(Recommendation, CloudAccount)
    async with session_factory() as db, TenantContext(ids["org_a"]):
        rows = (await db.execute(stmt)).all()

    assert rows, "expected org A's own row to survive the filter"
    leaked = [
        acc.id for _, acc in rows if acc.organization_id != ids["org_a"]
    ]
    assert not leaked, f"org B cloud accounts leaked into org A's query: {leaked}"


async def test_first_org_scoped_entity_is_also_filtered(orgs) -> None:
    """Order must not decide which side gets protected.

    Same statement with the entities swapped, so the *other* one is now the
    trailing mapper. Before the fix this leaked org A's recommendation into a
    query bound to org B.
    """
    ids, session_factory = orgs
    stmt = select(CloudAccount, Recommendation)
    async with session_factory() as db, TenantContext(ids["org_b"]):
        rows = (await db.execute(stmt)).all()

    assert rows
    for acc, rec in rows:
        assert acc.organization_id == ids["org_b"], "cloud account leaked"
        assert rec.organization_id == ids["org_b"], "recommendation leaked"


async def test_fk_join_stays_scoped(orgs) -> None:
    """The realistic join shape must keep working after the fix (no double-filter)."""
    ids, session_factory = orgs
    stmt = select(Recommendation, CloudAccount).join(
        CloudAccount, Recommendation.cloud_account_id == CloudAccount.id
    )
    async with session_factory() as db, TenantContext(ids["org_a"]):
        rows = (await db.execute(stmt)).all()

    assert len(rows) == 1, "expected exactly org A's own recommendation+account pair"
    rec, acc = rows[0]
    assert rec.organization_id == ids["org_a"]
    assert acc.organization_id == ids["org_a"]


async def test_no_context_returns_everything(orgs) -> None:
    """Without a bound org the listener stays out of the way (scheduler/seeder path)."""
    _ids, session_factory = orgs
    async with session_factory() as db:
        rows = (await db.execute(select(Recommendation))).scalars().all()
    assert len(rows) == 2
