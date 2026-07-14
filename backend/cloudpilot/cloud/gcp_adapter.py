"""GCP adapter — Cloud Billing + Cloud Monitoring (read-only).

In **demo mode** the adapter serves the shared fleet simulation. GCP rates are the
published list prices (the Cloud Billing Catalog API needs an API key, so unlike Azure
and AWS they are transcribed rather than fetched — and flagged as such in the catalog).

**No part of live mode is implemented for GCP.** Resource enumeration, billing and
metrics all raise. This adapter previously returned mock data from its live branch,
which meant a "connected" GCP project silently reported an estate that did not exist.
"""

from __future__ import annotations

import json
from datetime import date

from loguru import logger

from cloudpilot.cloud.base import (
    BillingEntryDTO,
    CloudProviderAdapter,
    MetricSampleDTO,
    ResourceDTO,
)
from cloudpilot.cloud.simulated import (
    simulated_billing,
    simulated_metrics,
    simulated_resources,
)
from cloudpilot.models.cloud_account import CloudProvider


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
            return simulated_resources("gcp")
        raise NotImplementedError(
            "Live GCP resource enumeration is not implemented. Wire the Compute Engine "
            "aggregatedList() call here."
        )

    async def get_billing(self, start: date, end: date) -> list[BillingEntryDTO]:
        if self.demo_mode:
            return simulated_billing("gcp", start, end)
        raise NotImplementedError(
            "Live GCP billing is not implemented. Wire the BigQuery billing-export query "
            "here. Until then, set DEMO_MODE=true."
        )

    async def get_metrics(
        self, provider_resource_id: str, metric: str, days: int
    ) -> list[MetricSampleDTO]:
        if self.demo_mode:
            return simulated_metrics("gcp", provider_resource_id, metric, days)
        raise NotImplementedError(
            "Live GCP metrics are not implemented. Wire Cloud Monitoring "
            "list_time_series() here."
        )
