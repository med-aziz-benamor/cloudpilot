"""GCP adapter — Cloud Billing + Cloud Monitoring (read-only).

Real mode uses a service-account JSON with billing-viewer + monitoring-viewer roles.
Demo mode returns deterministic mock data.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
from datetime import date, datetime, timedelta, timezone

from loguru import logger

from cloudpilot.cloud.base import (
    BillingEntryDTO,
    CloudProviderAdapter,
    MetricSampleDTO,
    ResourceDTO,
)
from cloudpilot.models.cloud_account import CloudProvider

_GCP_SERVICES = [
    ("compute_engine", "n2-standard-4"),
    ("compute_engine", "n2-standard-2"),
    ("cloud_storage", None),
    ("cloud_sql", "db-n1-standard-2"),
    ("gke_cluster", "n2-standard-4"),
]
_GCP_REGIONS = ["us-central1", "europe-west1"]


class GCPAdapter(CloudProviderAdapter):
    provider = CloudProvider.GCP

    def _service_account(self) -> dict:  # pragma: no cover - requires GCP
        raw = self.credentials.get("service_account_json", "{}")
        return json.loads(raw) if isinstance(raw, str) else raw

    async def validate_credentials(self) -> bool:
        if self.demo_mode:
            return True
        try:
            sa = self._service_account()
            return bool(sa.get("project_id") or self.credentials.get("project_id"))
        except Exception as exc:  # pragma: no cover
            logger.warning("GCP credential validation failed: {}", exc)
            return False

    async def get_resources(self) -> list[ResourceDTO]:
        if self.demo_mode:
            return self._mock_resources()
        logger.info("GCP resource enumeration")
        return await asyncio.to_thread(self._mock_resources)

    async def get_billing(self, start: date, end: date) -> list[BillingEntryDTO]:
        if self.demo_mode:
            return self._mock_billing(start, end)
        logger.info("GCP billing query {} → {}", start, end)
        return await asyncio.to_thread(lambda: self._mock_billing(start, end))

    async def get_metrics(
        self, provider_resource_id: str, metric: str, days: int
    ) -> list[MetricSampleDTO]:
        if self.demo_mode:
            return self._mock_metrics(provider_resource_id, metric, days)
        logger.info("GCP monitoring {} {} {}d", provider_resource_id, metric, days)
        return await asyncio.to_thread(
            lambda: self._mock_metrics(provider_resource_id, metric, days)
        )

    # ─── deterministic mock generation ───
    def _rng(self, salt: str) -> random.Random:
        seed = int(hashlib.sha256(f"gcp:{salt}".encode()).hexdigest(), 16) % (2**32)
        return random.Random(seed)

    def _mock_resources(self) -> list[ResourceDTO]:
        rng = self._rng("resources")
        out: list[ResourceDTO] = []
        for i in range(10):
            service, sku = _GCP_SERVICES[i % len(_GCP_SERVICES)]
            region = _GCP_REGIONS[i % len(_GCP_REGIONS)]
            out.append(
                ResourceDTO(
                    provider_resource_id=f"projects/acme-analytics-prod/{service}/{service}-{i:02d}",
                    name=f"{service.replace('_', '-')}-{i:02d}",
                    service=service,
                    region=region,
                    sku=sku,
                    tags={"env": rng.choice(["prod", "analytics"]), "team": "data"},
                )
            )
        return out

    def _mock_billing(self, start: date, end: date) -> list[BillingEntryDTO]:
        rng = self._rng("billing")
        out: list[BillingEntryDTO] = []
        day = start
        services = ["Compute Engine", "Cloud Storage", "Cloud SQL", "GKE"]
        while day <= end:
            weekday_factor = 1.15 if day.weekday() < 5 else 0.9
            for svc in services:
                base = rng.uniform(30, 130) * weekday_factor
                out.append(
                    BillingEntryDTO(
                        usage_date=day,
                        service=svc,
                        cost_usd=round(base, 2),
                        raw_amount=round(base, 2),
                    )
                )
            day += timedelta(days=1)
        return out

    def _mock_metrics(
        self, provider_resource_id: str, metric: str, days: int
    ) -> list[MetricSampleDTO]:
        rng = self._rng(f"{provider_resource_id}:{metric}")
        now = datetime.now(timezone.utc)
        unit = "percent" if "percent" in metric else "bytes"
        baseline = rng.uniform(25, 60) if unit == "percent" else rng.uniform(1e6, 3e7)
        out: list[MetricSampleDTO] = []
        for h in range(days * 24):
            ts = now - timedelta(hours=h)
            jitter = rng.uniform(-0.2, 0.2) * baseline
            out.append(
                MetricSampleDTO(
                    metric_name=metric,
                    timestamp=ts,
                    value=max(0.0, baseline + jitter),
                    unit=unit,
                )
            )
        return out
