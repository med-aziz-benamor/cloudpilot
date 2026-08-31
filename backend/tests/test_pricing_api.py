"""The rate card must be inspectable, and honest about its own age.

Provenance that only exists in a JSON blob nobody can reach is provenance in name
only. These tests pin the contract the UI reads: every rate carries where it came
from, and the snapshot says how old it is rather than presenting itself as current.

No database is involved — the catalog is public rate-card data, shared by every
tenant — so only the authenticated-user dependency is overridden.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from cloudpilot.api.deps import get_current_user
from cloudpilot.main import app
from cloudpilot.models.user import User, UserRole
from cloudpilot.pricing.models import STALE_AFTER_DAYS, CatalogMeta

URL = "/api/v1/pricing/catalog"


@pytest.fixture
async def client():
    """A client authenticated as the least-privileged role.

    Viewer, deliberately: reading the rate card is what makes a quoted saving
    checkable, so the role that can only look must still be able to.
    """
    def _viewer() -> User:
        return User(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            email="viewer@acme.test",
            password_hash="not-used",
            full_name="Viewer",
            role=UserRole.VIEWER,
        )

    app.dependency_overrides[get_current_user] = _viewer
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


async def test_catalog_requires_authentication() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        assert (await c.get(URL)).status_code in (401, 403)


async def test_catalog_exposes_every_rate_with_its_provenance(client) -> None:
    body = (await client.get(URL)).json()

    assert body["total_count"] == len(body["rates"])
    assert body["rates"], "the catalog must not be served empty"
    for rate in body["rates"]:
        assert rate["amount"] > 0
        assert rate["unit"] in {"hour", "gb_month"}
        assert rate["source"], f"{rate['sku']} has no provenance"
        assert rate["region"]
        assert rate["currency"] == "USD"


async def test_api_verified_flag_matches_the_source(client) -> None:
    """The badge the UI draws must be derived from the source, not asserted twice."""
    api_sources = {"azure_retail_api", "aws_price_list"}
    body = (await client.get(URL)).json()

    for rate in body["rates"]:
        assert rate["api_verified"] is (rate["source"] in api_sources)

    verified = sum(1 for r in body["rates"] if r["api_verified"])
    assert body["api_verified_count"] == verified
    assert body["api_verified_pct"] == pytest.approx(
        verified / body["total_count"] * 100, abs=0.1
    )


async def test_snapshot_reports_its_own_age(client) -> None:
    body = (await client.get(URL)).json()

    assert body["age_days"] >= 0
    assert body["stale_after_days"] == STALE_AFTER_DAYS
    assert body["is_stale"] is (body["age_days"] > STALE_AFTER_DAYS)
    assert body["regions"], "a rate is meaningless without the region it was quoted in"


def test_staleness_flips_at_the_threshold() -> None:
    """A card one day past the window is stale; one day inside it is not.

    Pinned because the whole point of the as-of date is that an old rate becomes
    *visible*, and an off-by-one here would keep a year-old card looking current.
    """
    def meta(age_days: int) -> CatalogMeta:
        return CatalogMeta(
            generated_at=datetime.now().astimezone() - timedelta(days=age_days),
            regions={"azure": "westeurope"},
            api_verified_count=1,
            total_count=2,
        )

    assert meta(STALE_AFTER_DAYS).is_stale is False
    assert meta(STALE_AFTER_DAYS + 1).is_stale is True


def test_age_is_never_negative_on_a_future_dated_snapshot() -> None:
    """Clock skew on the machine that ran the refresh must not read as "-3 days"."""
    future = CatalogMeta(
        generated_at=datetime.now().astimezone() + timedelta(days=3),
        regions={},
        api_verified_count=0,
        total_count=0,
    )
    assert future.age_days == 0
    assert future.is_stale is False
