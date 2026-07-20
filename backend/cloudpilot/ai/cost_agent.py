"""CostAgent — billing anomaly detection.

Algorithm:
1. Load ~60 days of daily billing grouped by (cloud_account, service).
2. For each group with >= 14 points, fit an IsolationForest (contamination=0.05)
   and additionally flag any day where cost > mu + 2*sigma (Z-score backup).
3. For each flagged day, build a root-cause explanation and a recommendation.
4. Deduplicate against existing pending cost recommendations.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
from loguru import logger
from sklearn.ensemble import IsolationForest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloudpilot.ai.base_agent import AgentBase
from cloudpilot.models.billing_entry import BillingEntry
from cloudpilot.models.cloud_account import CloudAccount, CloudProvider
from cloudpilot.models.recommendation import (
    AgentType,
    Recommendation,
    RecommendationStatus,
)

_LOOKBACK_DAYS = 60
_MIN_POINTS = 14

#: Materiality gates applied *after* statistical detection. IsolationForest and the
#: 2σ Z-score decide whether a day is anomalous; these decide whether it is worth a
#: human's attention.
#:
#: The percentage gate used to be 50, calibrated when costs were fabricated
#: arithmetically (``cost *= 4.4`` applied to a whole series, which trivially cleared
#: any percentage). Costs are now ``published_rate × simulated_usage``, so an anomaly
#: is physical and confined to one resource — but detection groups by
#: (account, service), which means the spike arrives *diluted by its siblings*.
#:
#: Measured on the seeded estate: the rds-production incident (a real 4x event) is
#: only 20% of its service group and lands at +57%, clearing the old gate by 7
#: points. Adding a single comparable RDS instance drops it to +48% and the
#: recommendation disappears — while its Z-score stays pinned at 5.12. The
#: percentage was eroding with estate size even though the signal was not.
#:
#: Sweeping the gate from 50% down to 10% surfaced zero additional unexplained
#: anomalies, so the gate was buying no noise reduction to pay for that. Lowered to
#: 25% and paired with an absolute floor, which is the gate that actually expresses
#: "material" — a 30% spike on a $2/day service is noise no matter the percentage.
_MIN_PCT_ABOVE_BASELINE = 25.0
_MIN_DELTA_USD = 5.0


class CostAgent(AgentBase):
    name = "CostAgent"
    description = "Detects billing anomalies (>2σ from the rolling 30-day baseline)."
    agent_type = AgentType.COST

    async def run(self, organization_id: uuid.UUID, db: AsyncSession) -> int:
        accounts = (
            (await db.execute(select(CloudAccount).where(
                CloudAccount.organization_id == organization_id
            ))).scalars().all()
        )
        if not accounts:
            return 0

        account_by_id = {a.id: a for a in accounts}
        since = date.today() - timedelta(days=_LOOKBACK_DAYS)
        rows = (
            (await db.execute(
                select(BillingEntry).where(
                    BillingEntry.cloud_account_id.in_(list(account_by_id)),
                    BillingEntry.usage_date >= since,
                )
            )).scalars().all()
        )

        # Group daily totals by (account, service).
        grouped: dict[tuple[uuid.UUID, str], dict[date, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for r in rows:
            grouped[(r.cloud_account_id, r.service)][r.usage_date] += float(r.cost_usd)

        existing = await self._pending_anomaly_dates(db, organization_id)
        created = 0

        for (account_id, service), daily in grouped.items():
            if len(daily) < _MIN_POINTS:
                continue
            dates = sorted(daily)
            values = np.array([daily[d] for d in dates], dtype=float)
            flagged = self._detect(dates, values)
            account = account_by_id[account_id]

            for idx in flagged:
                anomaly_date = dates[idx]
                key = (service, anomaly_date.isoformat())
                if key in existing:
                    continue
                actual = float(values[idx])
                baseline = float(np.mean(np.delete(values, idx)))
                if baseline <= 0:
                    continue
                delta = actual - baseline
                pct = (delta / baseline) * 100.0
                # Both gates must hold: materially large *and* materially expensive.
                if pct < _MIN_PCT_ABOVE_BASELINE or delta < _MIN_DELTA_USD:
                    continue
                std = float(np.std(values)) or 1.0
                z = delta / std
                confidence = min(0.95, 0.6 + max(0.0, z - 2) * 0.1)

                rec = Recommendation(
                    organization_id=organization_id,
                    cloud_account_id=account_id,
                    agent=AgentType.COST,
                    title=f"Unusual spend on {service} — {account.provider.value.upper()}",
                    description=(
                        f"On {anomaly_date.isoformat()}, {service} on "
                        f"{account.provider.value} spent ${actual:,.0f} which is "
                        f"{pct:.0f}% above the {len(dates)}-day baseline of "
                        f"${baseline:,.0f}."
                    ),
                    estimated_saving_usd=Decimal(str(round(max(delta, 0), 2))),
                    confidence=round(confidence, 2),
                    status=RecommendationStatus.PENDING,
                    metadata_json={
                        "anomaly_date": anomaly_date.isoformat(),
                        "service": service,
                        "provider": account.provider.value,
                        "expected_cost": round(baseline, 2),
                        "actual_cost": round(actual, 2),
                        "delta_usd": round(delta, 2),
                        "z_score": round(z, 2),
                    },
                )
                db.add(rec)
                existing.add(key)
                created += 1

        await db.flush()
        logger.info("CostAgent created {} recommendations for org {}", created, organization_id)
        return created

    def _detect(self, dates: list[date], values: np.ndarray) -> list[int]:
        """Return indices flagged by IsolationForest ∪ Z-score(>2σ)."""
        flagged: set[int] = set()

        # IsolationForest
        try:
            model = IsolationForest(contamination=0.05, random_state=42)
            preds = model.fit_predict(values.reshape(-1, 1))
            scores = model.score_samples(values.reshape(-1, 1))
            for i, (p, s) in enumerate(zip(preds, scores, strict=True)):
                if p == -1 and s < -0.1:
                    flagged.add(i)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("IsolationForest failed, using Z-score only: {}", exc)

        # Z-score backup
        mu, sigma = float(np.mean(values)), float(np.std(values))
        if sigma > 0:
            for i, v in enumerate(values):
                if v > mu + 2 * sigma:
                    flagged.add(i)

        return sorted(flagged)

    async def _pending_anomaly_dates(
        self, db: AsyncSession, organization_id: uuid.UUID
    ) -> set[tuple[str, str]]:
        rows = (
            (await db.execute(
                select(Recommendation).where(
                    Recommendation.organization_id == organization_id,
                    Recommendation.agent == AgentType.COST,
                    Recommendation.status == RecommendationStatus.PENDING,
                )
            )).scalars().all()
        )
        out: set[tuple[str, str]] = set()
        for r in rows:
            md = r.metadata_json or {}
            if md.get("service") and md.get("anomaly_date"):
                out.add((md["service"], md["anomaly_date"]))
        return out
