"""Forecast service — reads persisted forecast snapshots (does not run Prophet)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount
from cloudpilot.models.forecast_snapshot import ForecastSnapshot
from cloudpilot.models.organization import Organization
from cloudpilot.schemas.forecast import ForecastPoint, ForecastResponse


class ForecastService:
    def __init__(self, db: AsyncSession, organization_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = organization_id

    async def get_forecast(self, horizon_days: int = 30) -> ForecastResponse:
        snapshot = (
            await self.db.execute(
                select(ForecastSnapshot)
                .where(
                    ForecastSnapshot.organization_id == self.org_id,
                    ForecastSnapshot.horizon_days == horizon_days,
                )
                .order_by(desc(ForecastSnapshot.snapshot_date))
                .limit(1)
            )
        ).scalar_one_or_none()

        actuals = await self._actuals()
        mtd = await self._mtd()

        if snapshot is None:
            # No snapshot yet (ForecastAgent hasn't run) — degrade gracefully.
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="No forecast available yet. The ForecastAgent runs daily.",
            )

        data = snapshot.forecast_json
        points = [
            ForecastPoint(
                ds=date.fromisoformat(d),
                yhat=data["yhat"][i],
                yhat_lower=data["yhat_lower"][i],
                yhat_upper=data["yhat_upper"][i],
                trend=data["trend"][i],
            )
            for i, d in enumerate(data["dates"])
        ]

        # Projected month-end = MTD + sum of forecast points within this month.
        today = date.today()
        month_end = self._month_end(today)
        projected = mtd + sum(
            p.yhat for p in points if today < p.ds <= month_end and p.yhat > 0
        )
        next_90d = await self._next_90d_projection()

        # The tenant's own budget, not a constant. This used to be a hardcoded
        # $45,000 for every organization while ForecastAgent's overrun alerts
        # read `organizations.monthly_budget_usd` — so on the seeded demo the
        # Forecast page reported "within budget" against $45,000 while the
        # Recommendations page carried a live overrun alert against the real
        # $7,500. Same data, two screens, opposite verdicts.
        budget = await self.get_budget()
        if budget:
            over = projected > budget
            overrun = ((projected / budget) - 1) * 100
        else:
            # No budget on file: report the projection and say nothing about
            # whether it is "over" — there is nothing to be over.
            over = False
            overrun = 0.0

        return ForecastResponse(
            snapshot_date=snapshot.snapshot_date,
            horizon_days=horizon_days,
            current_mtd_usd=round(mtd, 2),
            projected_month_end_usd=round(projected, 2),
            budget_usd=budget,
            over_budget=over,
            overrun_pct=round(overrun, 1),
            next_90d_usd=round(next_90d, 2),
            points=points,
            actuals=actuals,
        )

    async def get_budget(self) -> float | None:
        """Return the tenant's monthly budget, or None if none is set."""
        org = await self.db.get(Organization, self.org_id)
        if org is None or org.monthly_budget_usd is None:
            return None
        return float(org.monthly_budget_usd)

    async def set_budget(self, budget_usd: float) -> float:
        """Set the tenant's monthly budget and return the stored value."""
        org = await self.db.get(Organization, self.org_id)
        if org is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found.")
        org.monthly_budget_usd = Decimal(str(round(budget_usd, 2)))
        await self.db.flush()
        return float(org.monthly_budget_usd)

    async def _account_ids(self) -> list[uuid.UUID]:
        return list(
            (
                await self.db.execute(
                    select(CloudAccount.id).where(
                        CloudAccount.organization_id == self.org_id
                    )
                )
            ).scalars().all()
        )

    async def _actuals(self) -> list[dict[str, Any]]:
        account_ids = await self._account_ids()
        if not account_ids:
            return []
        since = date.today() - timedelta(days=90)
        rows = (
            await self.db.execute(
                select(BillingEntry.usage_date, func.sum(BillingEntry.cost_usd))
                .where(
                    BillingEntry.cloud_account_id.in_(account_ids),
                    BillingEntry.usage_date >= since,
                )
                .group_by(BillingEntry.usage_date)
                .order_by(BillingEntry.usage_date)
            )
        ).all()
        return [{"ds": d.isoformat(), "y": round(float(c), 2)} for d, c in rows]

    async def _mtd(self) -> float:
        account_ids = await self._account_ids()
        if not account_ids:
            return 0.0
        month_start = date.today().replace(day=1)
        total = (
            await self.db.execute(
                select(func.coalesce(func.sum(BillingEntry.cost_usd), 0)).where(
                    BillingEntry.cloud_account_id.in_(account_ids),
                    BillingEntry.usage_date >= month_start,
                )
            )
        ).scalar_one()
        return float(total)

    async def _next_90d_projection(self) -> float:
        snapshot = (
            await self.db.execute(
                select(ForecastSnapshot)
                .where(
                    ForecastSnapshot.organization_id == self.org_id,
                    ForecastSnapshot.horizon_days == 90,
                )
                .order_by(desc(ForecastSnapshot.snapshot_date))
                .limit(1)
            )
        ).scalar_one_or_none()
        if not snapshot:
            return 0.0
        return float(sum(max(0.0, v) for v in snapshot.forecast_json.get("yhat", [])))

    @staticmethod
    def _month_end(d: date) -> date:
        if d.month == 12:
            return date(d.year, 12, 31)
        return date(d.year, d.month + 1, 1) - timedelta(days=1)
