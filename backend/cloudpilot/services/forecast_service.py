"""Forecast service — reads persisted forecast snapshots (does not run Prophet)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount
from cloudpilot.models.forecast_snapshot import ForecastSnapshot
from cloudpilot.schemas.forecast import ForecastPoint, ForecastResponse

_DEFAULT_BUDGET = 45_000.0


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
        over = projected > _DEFAULT_BUDGET
        overrun = ((projected / _DEFAULT_BUDGET) - 1) * 100 if _DEFAULT_BUDGET else 0.0

        return ForecastResponse(
            snapshot_date=snapshot.snapshot_date,
            horizon_days=horizon_days,
            current_mtd_usd=round(mtd, 2),
            projected_month_end_usd=round(projected, 2),
            budget_usd=_DEFAULT_BUDGET,
            over_budget=over,
            overrun_pct=round(overrun, 1),
            next_90d_usd=round(next_90d, 2),
            points=points,
            actuals=actuals,
        )

    async def _account_ids(self):
        return (
            await self.db.execute(
                select(CloudAccount.id).where(CloudAccount.organization_id == self.org_id)
            )
        ).scalars().all()

    async def _actuals(self) -> list[dict]:
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
