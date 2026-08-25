"""RBAC actually gates the endpoint groups it claims to, not just in isolation.

``core/rbac.py``'s own docstring says it is "the FIRST layer of authorization" —
but until this file, nothing proved that a route actually applies the guard.
Tenant isolation (``test_tenant_isolation*.py``) is heavily, mutation-verified
tested; RBAC had zero coverage despite gating 5 permission-sensitive endpoint
groups used across 4 route files. This introduces the suite's first HTTP-level
test client (via ``httpx.ASGITransport`` against the real FastAPI app) rather
than only unit-testing ``role_has_permission`` in isolation, because a unit
test of the permission function can't catch a route that forgot to apply the
guard at all — exactly the risk this file exists to cover.

Two things worth knowing before reading the cases below:

* ``users.manage`` is declared in the permission matrix but gates no endpoint
  anywhere in the codebase (confirmed by grep) — there is no user-management
  router. It is covered here as a direct unit test against
  ``role_has_permission``, not an HTTP case, so its absence doesn't read as an
  oversight.
* ``agents.trigger`` is gated (``POST /admin/agents/{agent}/run``) but wasn't
  in the original audit's finding list; it's covered here too since the
  fixtures already exist and it is a real gated endpoint.

Gated behind ``CLOUDPILOT_TEST_DB`` like the rest of the DB-backed suite, and
now also requires Redis reachable (``core/rate_limit.is_revoked`` fails
*closed* since the 2026-08-25 hardening pass — see docs/session-report — so a
missing Redis makes every authenticated request 401, not a silent pass).

Mutation-verified while authoring: temporarily inverting
``role_has_permission``'s ``role in allowed`` to ``role not in allowed`` turns
every "allow" case in this file red and leaves every "deny" case green, then
reverting restores the original (all-green) result — confirming these tests
actually exercise the guard rather than passing regardless of it.
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cloudpilot.api.deps import get_db
from cloudpilot.core import rate_limit
from cloudpilot.core.rbac import role_has_permission
from cloudpilot.core.security import create_access_token
from cloudpilot.database import Base
from cloudpilot.main import app
from cloudpilot.models.cloud_account import CloudAccount, CloudProvider
from cloudpilot.models.organization import Organization
from cloudpilot.models.recommendation import AgentType, Recommendation, RecommendationStatus
from cloudpilot.models.user import User, UserRole

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
    "agent_run_logs",
    "audit_log",
    "chat_sessions",
    "chat_messages",
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


@pytest.fixture
async def org_and_client(session_factory):
    """One organization with an admin/analyst/viewer user each, and an HTTP
    client wired to the real app with `get_db` overridden onto the test
    engine. Returns (client, org_id, tokens) where tokens maps role -> bearer
    token minted directly (bypassing login/bcrypt — RBAC, not auth, is under
    test here)."""

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
    # rate_limit's module-level Redis client is a singleton bound to whichever
    # event loop first created it. pytest-asyncio gives each test its own
    # loop, so a client created by an earlier test raises "Event loop is
    # closed" here — reset it so this test builds its own against its loop.
    rate_limit._client = None

    async with session_factory() as db:
        org = Organization(name="Acme")
        db.add(org)
        await db.flush()
        org_id = org.id

        users = {}
        for role in (UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER):
            user = User(
                organization_id=org_id,
                email=f"{role.value}@acme.test",
                password_hash="not-used",
                full_name=role.value.title(),
                role=role,
            )
            db.add(user)
            await db.flush()
            users[role] = user.id
        await db.commit()

    tokens = {
        role: create_access_token(user_id, org_id, role.value)
        for role, user_id in users.items()
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, org_id, tokens

    app.dependency_overrides.pop(get_db, None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ─── chat.use: analyst + admin allowed, viewer denied ───
async def test_viewer_cannot_list_chat_sessions(org_and_client) -> None:
    client, _, tokens = org_and_client
    resp = await client.get("/api/v1/chat/sessions", headers=_auth(tokens[UserRole.VIEWER]))
    assert resp.status_code == 403


async def test_analyst_can_list_chat_sessions(org_and_client) -> None:
    client, _, tokens = org_and_client
    resp = await client.get("/api/v1/chat/sessions", headers=_auth(tokens[UserRole.ANALYST]))
    assert resp.status_code == 200
    assert resp.json() == []


# ─── recommendations.write: analyst + admin allowed, viewer denied ───
async def test_viewer_cannot_update_recommendation_status(
    session_factory, org_and_client
) -> None:
    client, org_id, tokens = org_and_client
    async with session_factory() as db:
        rec = Recommendation(
            organization_id=org_id,
            agent=AgentType.COST,
            title="Unusual spend",
            description="test",
            confidence=0.9,
            status=RecommendationStatus.PENDING,
        )
        db.add(rec)
        await db.commit()
        rec_id = rec.id

    resp = await client.patch(
        f"/api/v1/recommendations/{rec_id}/status",
        json={"status": "accepted"},
        headers=_auth(tokens[UserRole.VIEWER]),
    )
    assert resp.status_code == 403


async def test_analyst_can_update_recommendation_status(
    session_factory, org_and_client
) -> None:
    client, org_id, tokens = org_and_client
    async with session_factory() as db:
        rec = Recommendation(
            organization_id=org_id,
            agent=AgentType.COST,
            title="Unusual spend",
            description="test",
            confidence=0.9,
            status=RecommendationStatus.PENDING,
        )
        db.add(rec)
        await db.commit()
        rec_id = rec.id

    resp = await client.patch(
        f"/api/v1/recommendations/{rec_id}/status",
        json={"status": "accepted"},
        headers=_auth(tokens[UserRole.ANALYST]),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"


# ─── cloud_accounts.manage: admin-only, analyst AND viewer denied ───
async def test_viewer_cannot_delete_cloud_account(session_factory, org_and_client) -> None:
    client, org_id, tokens = org_and_client
    async with session_factory() as db:
        account = CloudAccount(
            organization_id=org_id,
            provider=CloudProvider.AZURE,
            display_name="acct",
            account_identifier="sub-1",
            credentials_enc="",
        )
        db.add(account)
        await db.commit()
        account_id = account.id

    resp = await client.delete(
        f"/api/v1/cloud-accounts/{account_id}", headers=_auth(tokens[UserRole.VIEWER])
    )
    assert resp.status_code == 403


async def test_analyst_cannot_delete_cloud_account(session_factory, org_and_client) -> None:
    """cloud_accounts.manage is admin-only — analyst must also be denied."""
    client, org_id, tokens = org_and_client
    async with session_factory() as db:
        account = CloudAccount(
            organization_id=org_id,
            provider=CloudProvider.AZURE,
            display_name="acct",
            account_identifier="sub-1",
            credentials_enc="",
        )
        db.add(account)
        await db.commit()
        account_id = account.id

    resp = await client.delete(
        f"/api/v1/cloud-accounts/{account_id}", headers=_auth(tokens[UserRole.ANALYST])
    )
    assert resp.status_code == 403


async def test_admin_can_delete_cloud_account(session_factory, org_and_client) -> None:
    client, org_id, tokens = org_and_client
    async with session_factory() as db:
        account = CloudAccount(
            organization_id=org_id,
            provider=CloudProvider.AZURE,
            display_name="acct",
            account_identifier="sub-1",
            credentials_enc="",
        )
        db.add(account)
        await db.commit()
        account_id = account.id

    resp = await client.delete(
        f"/api/v1/cloud-accounts/{account_id}", headers=_auth(tokens[UserRole.ADMIN])
    )
    assert resp.status_code == 200


# ─── audit.read: admin-only ───
async def test_viewer_cannot_read_audit_log(org_and_client) -> None:
    client, _, tokens = org_and_client
    resp = await client.get(
        "/api/v1/admin/audit-log", headers=_auth(tokens[UserRole.VIEWER])
    )
    assert resp.status_code == 403


async def test_admin_can_read_audit_log(org_and_client) -> None:
    client, _, tokens = org_and_client
    resp = await client.get(
        "/api/v1/admin/audit-log", headers=_auth(tokens[UserRole.ADMIN])
    )
    assert resp.status_code == 200
    assert resp.json() == []


# ─── agents.trigger: admin-only (gated, but not in the original audit list) ───
async def test_viewer_cannot_trigger_agents(org_and_client) -> None:
    client, _, tokens = org_and_client
    resp = await client.post(
        "/api/v1/admin/agents/cost/run", headers=_auth(tokens[UserRole.VIEWER])
    )
    assert resp.status_code == 403


async def test_admin_can_trigger_agents(org_and_client) -> None:
    client, _, tokens = org_and_client
    # A fresh org has no cloud accounts, so CostAgent.run() returns 0 fast —
    # RBAC is what's under test here, not agent output.
    resp = await client.post(
        "/api/v1/admin/agents/cost/run", headers=_auth(tokens[UserRole.ADMIN])
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == 0


# ─── users.manage: gates no endpoint anywhere — unit-tested directly ───
def test_users_manage_permission_is_admin_only() -> None:
    assert role_has_permission(UserRole.ADMIN, "users.manage") is True
    assert role_has_permission(UserRole.ANALYST, "users.manage") is False
    assert role_has_permission(UserRole.VIEWER, "users.manage") is False
