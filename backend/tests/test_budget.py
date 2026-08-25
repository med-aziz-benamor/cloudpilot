"""The forecast budget must be the tenant's own, and settable.

Two things under test:

1. `ForecastService` used a module-level ``_DEFAULT_BUDGET = 45_000.0`` for
   every organization, while `ForecastAgent` has always read
   ``organizations.monthly_budget_usd``. On the seeded demo (a $7,500 budget)
   that put the Forecast page's "within budget" verdict in direct
   contradiction with a live ForecastAgent overrun recommendation quoting the
   real $7,500 — same data, two screens, opposite answers.
2. There was no write path at all: the column existed, the seeder set it, and
   nothing else could change it.

Gated behind ``CLOUDPILOT_TEST_DB`` like the rest of the DB-backed suite.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cloudpilot.api.deps import get_db
from cloudpilot.core import rate_limit
from cloudpilot.core.security import create_access_token
from cloudpilot.database import Base
from cloudpilot.main import app
from cloudpilot.models.organization import Organization
from cloudpilot.models.user import User, UserRole
from cloudpilot.services.forecast_service import ForecastService

TEST_DB_URL = os.environ.get("CLOUDPILOT_TEST_DB")

pytestmark = pytest.mark.skipif(
    not TEST_DB_URL, reason="CLOUDPILOT_TEST_DB not set; skipping DB-backed tests"
)

_TABLES = [
    "organizations",
    "users",
    "cloud_accounts",
    "resources",
    "billing_entries",
    "recommendations",
    "forecast_snapshots",
    "audit_log",
]


@pytest.fixture
async def session_factory():
    eng = create_async_engine(TEST_DB_URL, future=True, poolclass=NullPool)
    tables = [Base.metadata.tables[t] for t in _TABLES]
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    yield async_sessionmaker(bind=eng, expire_on_commit=False)
    await eng.dispose()


async def test_get_budget_returns_the_tenants_own_value(session_factory) -> None:
    async with session_factory() as db:
        org = Organization(name="Acme", monthly_budget_usd=Decimal("7500.00"))
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.commit()

    async with session_factory() as db:
        budget = await ForecastService(db, org_id).get_budget()

    # The number the seeder actually set — not the old hardcoded 45_000.
    assert budget == 7500.0


async def test_get_budget_is_none_when_unset(session_factory) -> None:
    async with session_factory() as db:
        org = Organization(name="NoBudget")
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.commit()

    async with session_factory() as db:
        assert await ForecastService(db, org_id).get_budget() is None


async def test_set_budget_persists(session_factory) -> None:
    async with session_factory() as db:
        org = Organization(name="Acme", monthly_budget_usd=Decimal("7500.00"))
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.commit()

    async with session_factory() as db:
        stored = await ForecastService(db, org_id).set_budget(9000.0)
        await db.commit()
    assert stored == 9000.0

    async with session_factory() as db:
        assert await ForecastService(db, org_id).get_budget() == 9000.0


# ─── HTTP layer: permission + audit ───
@pytest.fixture
async def client_and_org(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    rate_limit._client = None  # see test_rbac.py — singleton bound to one event loop

    async with session_factory() as db:
        org = Organization(name="Acme", monthly_budget_usd=Decimal("7500.00"))
        db.add(org)
        await db.flush()
        org_id = org.id
        users = {}
        for role in (UserRole.ADMIN, UserRole.VIEWER):
            user = User(
                organization_id=org_id,
                email=f"{role.value}@acme.test",
                password_hash="not-used",
                full_name=role.value,
                role=role,
            )
            db.add(user)
            await db.flush()
            users[role] = user.id
        await db.commit()

    tokens = {r: create_access_token(uid, org_id, r.value) for r, uid in users.items()}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, org_id, tokens
    app.dependency_overrides.pop(get_db, None)


async def test_viewer_cannot_set_the_budget(client_and_org) -> None:
    client, _, tokens = client_and_org
    resp = await client.patch(
        "/api/v1/forecast/budget",
        json={"budget_usd": 1234},
        headers={"Authorization": f"Bearer {tokens[UserRole.VIEWER]}"},
    )
    assert resp.status_code == 403


async def test_admin_can_set_the_budget(client_and_org) -> None:
    client, _, tokens = client_and_org
    resp = await client.patch(
        "/api/v1/forecast/budget",
        json={"budget_usd": 12345.67},
        headers={"Authorization": f"Bearer {tokens[UserRole.ADMIN]}"},
    )
    assert resp.status_code == 200
    assert resp.json()["budget_usd"] == 12345.67


async def test_budget_update_rejects_unpersistable_fields(client_and_org) -> None:
    """The old BudgetUpdate schema accepted threshold/alert fields that had no
    column to live in. extra='forbid' must now reject them rather than
    silently dropping what the caller sent."""
    client, _, tokens = client_and_org
    resp = await client.patch(
        "/api/v1/forecast/budget",
        json={"budget_usd": 100, "alerts_enabled": False},
        headers={"Authorization": f"Bearer {tokens[UserRole.ADMIN]}"},
    )
    assert resp.status_code == 422


async def test_negative_budget_is_rejected(client_and_org) -> None:
    client, _, tokens = client_and_org
    resp = await client.patch(
        "/api/v1/forecast/budget",
        json={"budget_usd": -1},
        headers={"Authorization": f"Bearer {tokens[UserRole.ADMIN]}"},
    )
    assert resp.status_code == 422


async def test_setting_the_budget_writes_an_audit_row(client_and_org) -> None:
    client, org_id, tokens = client_and_org
    await client.patch(
        "/api/v1/forecast/budget",
        json={"budget_usd": 8000},
        headers={"Authorization": f"Bearer {tokens[UserRole.ADMIN]}"},
    )
    resp = await client.get(
        "/api/v1/admin/audit-log",
        headers={"Authorization": f"Bearer {tokens[UserRole.ADMIN]}"},
    )
    events = [row["event_type"] for row in resp.json()]
    assert "budget.update" in events
