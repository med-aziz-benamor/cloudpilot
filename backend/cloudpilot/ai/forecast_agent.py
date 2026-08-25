"""ForecastAgent — cost forecasting with Prophet.

Algorithm:
1. Load 90+ days of daily org-wide billing totals.
2. Fit Prophet (weekly seasonality on, yearly/daily off) with a month-end regressor.
3. Predict 30/60/90 days ahead and persist a forecast_snapshots row per horizon.
4. If the projected month-end exceeds budget * 1.10, raise a recommendation.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.ai.base_agent import AgentBase
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount
from cloudpilot.models.forecast_snapshot import ForecastSnapshot
from cloudpilot.models.organization import Organization
from cloudpilot.models.recommendation import (
    AgentType,
    Recommendation,
    RecommendationStatus,
)

#: Fire the alert once the projection exceeds the budget by this margin, so a
#: forecast that lands a rounding error over budget does not page anyone.
_OVERRUN_TRIGGER = 1.10

#: How much billing history to load. Deliberately not CostAgent's 60-day
#: _LOOKBACK_DAYS: Prophet's weekly-seasonality fit and this module's own
#: "90+ days" premise want more history than that, so this is sized to cover a
#: full seasonal cycle (just over a year) rather than reusing a shorter
#: constant sized for a different agent's needs.
_LOOKBACK_DAYS = 400


class ForecastAgent(AgentBase):
    name = "ForecastAgent"
    description = "Predicts cloud spend 30/60/90 days ahead using Prophet."
    agent_type = AgentType.FORECAST

    async def run(self, organization_id: uuid.UUID, db: AsyncSession) -> int:
        daily = await self._daily_totals(db, organization_id)
        if len(daily) < 30:
            logger.info("ForecastAgent: not enough history for org {}", organization_id)
            return 0

        df = pd.DataFrame(
            {"ds": list(daily.keys()), "y": list(daily.values())}
        ).sort_values("ds")
        df["month_end"] = df["ds"].apply(lambda d: 1.0 if d.day >= 26 else 0.0)

        model = self._fit(df)
        today = date.today()

        # Persist snapshots for each horizon.
        for horizon in (30, 60, 90):
            forecast = self._predict(model, df, horizon)
            await self._upsert_snapshot(db, organization_id, today, horizon, forecast)

        # Budget overrun check on the 30-day horizon.
        created = await self._maybe_budget_alert(db, organization_id, model, df)
        await db.flush()
        return created

    def _fit(self, df: pd.DataFrame):
        from prophet import Prophet

        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.8,
        )
        model.add_regressor("month_end")
        # Prophet logs verbosely; keep it quiet.
        import logging

        logging.getLogger("prophet").setLevel(logging.WARNING)
        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
        model.fit(df[["ds", "y", "month_end"]])
        return model

    def _predict(self, model, df: pd.DataFrame, horizon: int) -> dict:
        future = model.make_future_dataframe(periods=horizon)
        future["month_end"] = future["ds"].apply(lambda d: 1.0 if d.day >= 26 else 0.0)
        fc = model.predict(future).tail(horizon)
        return {
            "dates": [d.date().isoformat() for d in fc["ds"]],
            "yhat": [round(float(v), 2) for v in fc["yhat"]],
            "yhat_lower": [round(float(v), 2) for v in fc["yhat_lower"]],
            "yhat_upper": [round(float(v), 2) for v in fc["yhat_upper"]],
            "trend": [round(float(v), 2) for v in fc["trend"]],
        }

    async def _upsert_snapshot(
        self,
        db: AsyncSession,
        organization_id: uuid.UUID,
        snapshot_date: date,
        horizon: int,
        forecast: dict,
    ) -> None:
        existing = (
            await db.execute(
                select(ForecastSnapshot).where(
                    ForecastSnapshot.organization_id == organization_id,
                    ForecastSnapshot.snapshot_date == snapshot_date,
                    ForecastSnapshot.horizon_days == horizon,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.forecast_json = forecast
        else:
            db.add(
                ForecastSnapshot(
                    organization_id=organization_id,
                    snapshot_date=snapshot_date,
                    horizon_days=horizon,
                    forecast_json=forecast,
                )
            )

    async def _maybe_budget_alert(
        self, db: AsyncSession, organization_id: uuid.UUID, model, df: pd.DataFrame
    ) -> int:
        """Raise an overrun alert only against a budget the tenant actually set."""
        org = await db.get(Organization, organization_id)
        if org is None or org.monthly_budget_usd is None:
            # No budget on file. Alerting against an invented figure is noise — which
            # is exactly what a single hardcoded constant produced for every tenant.
            logger.info(
                "ForecastAgent: org {} has no monthly budget set; skipping overrun check.",
                organization_id,
            )
            return 0
        budget = float(org.monthly_budget_usd)

        today = date.today()
        days_left = (self._month_end(today) - today).days
        # Both month AND year: matching on month alone means that once an org
        # has more than 12 months of billing history, "month-to-date" silently
        # sums cost from every past year sharing today's month number too.
        mtd = float(
            df[df["ds"].apply(lambda d: d.month == today.month and d.year == today.year)][
                "y"
            ].sum()
        )

        if days_left > 0:
            future = model.make_future_dataframe(periods=days_left)
            future["month_end"] = future["ds"].apply(
                lambda d: 1.0 if d.day >= 26 else 0.0
            )
            fc = model.predict(future).tail(days_left)
            remaining = float(fc["yhat"].clip(lower=0).sum())
        else:
            remaining = 0.0
        projected = mtd + remaining

        if projected <= budget * _OVERRUN_TRIGGER:
            return 0

        # Avoid duplicate pending budget alerts.
        dup = (
            await db.execute(
                select(Recommendation).where(
                    Recommendation.organization_id == organization_id,
                    Recommendation.agent == AgentType.FORECAST,
                    Recommendation.status == RecommendationStatus.PENDING,
                )
            )
        ).scalars().first()
        if dup:
            return 0

        overrun_pct = (projected / budget - 1) * 100
        db.add(
            Recommendation(
                organization_id=organization_id,
                agent=AgentType.FORECAST,
                title=f"Projected budget overrun for {today.strftime('%B %Y')}",
                description=(
                    f"At current burn rate, this month projects to "
                    f"${projected:,.0f} ({overrun_pct:.0f}% over the "
                    f"${budget:,.0f} budget)."
                ),
                estimated_saving_usd=None,
                confidence=0.87,
                status=RecommendationStatus.PENDING,
                metadata_json={
                    "current_mtd": round(mtd, 2),
                    "projected_month_end": round(projected, 2),
                    "budget": budget,
                    "overrun_pct": round(overrun_pct, 1),
                },
            )
        )
        return 1

    async def _daily_totals(
        self, db: AsyncSession, organization_id: uuid.UUID
    ) -> dict[date, float]:
        account_ids = (
            (await db.execute(
                select(CloudAccount.id).where(
                    CloudAccount.organization_id == organization_id
                )
            )).scalars().all()
        )
        if not account_ids:
            return {}
        since = date.today() - timedelta(days=_LOOKBACK_DAYS)
        rows = (
            (await db.execute(
                select(BillingEntry.usage_date, BillingEntry.cost_usd).where(
                    BillingEntry.cloud_account_id.in_(account_ids),
                    BillingEntry.usage_date >= since,
                )
            )).all()
        )
        totals: dict[date, float] = defaultdict(float)
        for usage_date, cost in rows:
            totals[usage_date] += float(cost)
        return dict(sorted(totals.items()))

    @staticmethod
    def _month_end(d: date) -> date:
        if d.month == 12:
            return date(d.year, 12, 31)
        return date(d.year, d.month + 1, 1) - timedelta(days=1)
