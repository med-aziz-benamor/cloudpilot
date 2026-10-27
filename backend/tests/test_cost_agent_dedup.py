"""CostAgent anomaly dedup must be scoped per account, not just per service+date.

Before this fix, the dedup key was ``(service, date)`` with no account — so two
cloud accounts with an anomaly in the same service on the same day collided,
and the second account's real anomaly was silently dropped as a "duplicate".
This hit both places that build the key: the in-run set built while iterating
``grouped.items()``, and ``_pending_anomaly_dates()``'s reconstruction from
already-stored recommendations on a later run.

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
from cloudpilot.database import Base
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount, CloudProvider
from cloudpilot.models.organization import Organization
from cloudpilot.models.recommendation import Recommendation

TEST_DB_URL = os.environ.get("CLOUDPILOT_TEST_DB")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="CLOUDPILOT_TEST_DB not set; skipping DB-backed tests"
)

_TABLES = ["organizations", "cloud_accounts", "resources", "billing_entries", "recommendations"]


@pytest.fixture
async def session_factory():
    eng = create_async_engine(TEST_DB_URL, future=True, poolclass=NullPool)
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    yield async_sessionmaker(bind=eng, expire_on_commit=False)
    await eng.dispose()


async def _add_account_with_spike(
    db, org_id: uuid.UUID, name: str, service: str, spike_day_offset: int
) -> uuid.UUID:
    account = CloudAccount(
        organization_id=org_id,
        provider=CloudProvider.AZURE,
        display_name=name,
        account_identifier=f"sub-{name}",
        credentials_enc="",
    )
    db.add(account)
    await db.flush()

    today = date.today()
    for i in range(60):
        day = today - timedelta(days=i)
        cost = 500.0 if i == spike_day_offset else 100.0
        db.add(
            BillingEntry(
                organization_id=org_id,
                cloud_account_id=account.id,
                usage_date=day,
                service=service,
                cost_usd=Decimal(str(cost)),
                raw_currency="USD",
                raw_amount=Decimal(str(cost)),
            )
        )
    return account.id


async def test_two_accounts_same_service_same_day_both_get_flagged(session_factory) -> None:
    """Reproduces the in-run collision: both accounts spike on 'Kubernetes' on
    the same day within a single CostAgent.run() call."""
    async with session_factory() as db:
        org = Organization(name="Acme")
        db.add(org)
        await db.flush()
        org_id = org.id
        acct_a = await _add_account_with_spike(db, org_id, "acct-a", "Kubernetes", 5)
        acct_b = await _add_account_with_spike(db, org_id, "acct-b", "Kubernetes", 5)
        await db.commit()

    agent = CostAgent()
    async with session_factory() as db:
        created = await agent.run(org_id, db)
        await db.commit()

    assert created == 2, "both accounts' anomalies must surface, not just the first"

    async with session_factory() as db:
        recs = (await db.execute(select(Recommendation))).scalars().all()

    accounts_flagged = {r.cloud_account_id for r in recs}
    assert accounts_flagged == {acct_a, acct_b}


async def test_a_new_accounts_anomaly_is_not_hidden_by_another_accounts_stored_one(
    session_factory,
) -> None:
    """Reproduces the _pending_anomaly_dates collision: account A already has a
    stored recommendation for (Kubernetes, day 5) from a prior run; account B's
    genuinely new anomaly on the same service+day must still surface on the
    next run, not be treated as already covered by A's row."""
    async with session_factory() as db:
        org = Organization(name="Acme")
        db.add(org)
        await db.flush()
        org_id = org.id
        acct_a = await _add_account_with_spike(db, org_id, "acct-a", "Kubernetes", 5)
        await db.commit()

    agent = CostAgent()
    async with session_factory() as db:
        first_run_created = await agent.run(org_id, db)
        await db.commit()
    assert first_run_created == 1

    async with session_factory() as db:
        acct_b = await _add_account_with_spike(db, org_id, "acct-b", "Kubernetes", 5)
        await db.commit()

    async with session_factory() as db:
        second_run_created = await agent.run(org_id, db)
        await db.commit()

    assert second_run_created == 1, "account B's new anomaly must not be deduped against A's"

    async with session_factory() as db:
        recs = (await db.execute(select(Recommendation))).scalars().all()
    accounts_flagged = {r.cloud_account_id for r in recs}
    assert accounts_flagged == {acct_a, acct_b}
