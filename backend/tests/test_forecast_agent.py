"""ForecastAgent's month-to-date calculation must not ignore the year, and its
history query must be bounded.

Before this fix, ``_maybe_budget_alert``'s MTD filter matched on
``d.month == today.month`` only — dormant for a brand-new org, but once an
org accumulates more than 12 months of billing history, MTD would silently
sum cost from every past year sharing today's month number, inflating the
projected-overrun figure. Separately, ``_daily_totals`` had no date bound at
all, contradicting its own "load 90+ days" docstring.

Gated behind ``CLOUDPILOT_TEST_DB`` like the rest of the DB-backed suite.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cloudpilot.ai.forecast_agent import _LOOKBACK_DAYS, ForecastAgent
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


class _ZeroRemainderModel:
    """Fake Prophet model: forecasts $0 for every remaining day, so
    ``projected == mtd`` exactly and the test isolates the MTD calculation
    from Prophet's own forecasting behavior."""

    def make_future_dataframe(self, periods: int) -> pd.DataFrame:
        start = date.today() + timedelta(days=1)
        return pd.DataFrame({"ds": [start + timedelta(days=i) for i in range(periods)]})

    def predict(self, future: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"ds": future["ds"], "yhat": [0.0] * len(future)})


async def test_mtd_excludes_a_prior_years_same_month(session_factory) -> None:
    today = date.today()
    async with session_factory() as db:
        org = Organization(name="Acme", monthly_budget_usd=Decimal("1.00"))  # forces overrun
        db.add(org)
        await db.flush()
        org_id = org.id
        await db.commit()

    # This year's month-to-date: $50/day for the first 5 days of the month.
    this_year_days = [date(today.year, today.month, d) for d in range(1, 6)]
    # Three years ago, same month, same days — must NOT be counted as MTD.
    old_days = [date(today.year - 3, today.month, d) for d in range(1, 6)]

    df = pd.DataFrame(
        {
            "ds": this_year_days + old_days,
            "y": [50.0] * len(this_year_days) + [100_000.0] * len(old_days),
        }
    )

    agent = ForecastAgent()
    async with session_factory() as db:
        created = await agent._maybe_budget_alert(db, org_id, _ZeroRemainderModel(), df)
        await db.commit()

    assert created == 1
    async with session_factory() as db:
        from sqlalchemy import select

        rec = (
            await db.execute(select(Recommendation).where(Recommendation.organization_id == org_id))
        ).scalar_one()

    assert rec.metadata_json["current_mtd"] == pytest.approx(50.0 * len(this_year_days)), (
        "MTD pulled in the 3-years-ago rows sharing this month's number: "
        f"{rec.metadata_json['current_mtd']}"
    )


async def test_daily_totals_is_bounded_to_the_lookback_window(session_factory) -> None:
    today = date.today()
    async with session_factory() as db:
        org = Organization(name="Acme")
        db.add(org)
        await db.flush()
        org_id = org.id
        account = CloudAccount(
            organization_id=org_id,
            provider=CloudProvider.AZURE,
            display_name="acct",
            account_identifier="sub-1",
            credentials_enc="",
        )
        db.add(account)
        await db.flush()

        # One row well inside the lookback window, one row well outside it.
        db.add(
            BillingEntry(
                organization_id=org_id,
                cloud_account_id=account.id,
                usage_date=today - timedelta(days=10),
                service="Compute",
                cost_usd=Decimal("10.00"),
                raw_currency="USD",
                raw_amount=Decimal("10.00"),
            )
        )
        db.add(
            BillingEntry(
                organization_id=org_id,
                cloud_account_id=account.id,
                usage_date=today - timedelta(days=_LOOKBACK_DAYS + 30),
                service="Compute",
                cost_usd=Decimal("999.00"),
                raw_currency="USD",
                raw_amount=Decimal("999.00"),
            )
        )
        await db.commit()

    agent = ForecastAgent()
    async with session_factory() as db:
        daily = await agent._daily_totals(db, org_id)

    assert (today - timedelta(days=10)) in daily
    assert (today - timedelta(days=_LOOKBACK_DAYS + 30)) not in daily
