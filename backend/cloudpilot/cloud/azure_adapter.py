"""Azure adapter — resource inventory, Cost Management, Azure Monitor (read-only).

In **demo mode** the adapter serves the shared fleet simulation: synthetic usage
priced from the Azure Retail Prices API. See :mod:`cloudpilot.cloud.simulated`.

In **live mode** resource enumeration is real (ResourceManagementClient). Billing and
metrics are *not yet implemented* and raise rather than quietly returning simulated
figures — a fabricated cost presented as a real Azure invoice is worse than an error,
because the agents would raise anomalies against numbers that never existed.

The management SDKs are synchronous, so live calls are dispatched to a thread via
``asyncio.to_thread`` to keep the event loop free.
"""

from __future__ import annotations

import asyncio
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


class AzureAdapter(CloudProviderAdapter):
    provider = CloudProvider.AZURE

    async def validate_credentials(self) -> bool:
        if self.demo_mode:
            return True
        try:
            from azure.identity import ClientSecretCredential

            cred = ClientSecretCredential(
                tenant_id=self.credentials["tenant_id"],
                client_id=self.credentials["client_id"],
                client_secret=self.credentials["client_secret"],
            )
            # A token request is the cheapest way to prove the SP authenticates.
            await asyncio.to_thread(cred.get_token, "https://management.azure.com/.default")
            return True
        except Exception as exc:  # pragma: no cover - network/credentials
            logger.warning("Azure credential validation failed: {}", exc)
            return False

    async def get_resources(self) -> list[ResourceDTO]:
        if self.demo_mode:
            return simulated_resources("azure")
        # Real implementation sketch: enumerate via ResourceManagementClient.
        from azure.identity import ClientSecretCredential
        from azure.mgmt.resource import ResourceManagementClient

        def _list() -> list[ResourceDTO]:
            cred = ClientSecretCredential(
                tenant_id=self.credentials["tenant_id"],
                client_id=self.credentials["client_id"],
                client_secret=self.credentials["client_secret"],
            )
            client = ResourceManagementClient(
                cred, self.credentials["subscription_id"]
            )
            out: list[ResourceDTO] = []
            for r in client.resources.list():
                out.append(
                    ResourceDTO(
                        provider_resource_id=r.id,
                        name=r.name,
                        service=(r.type or "").split("/")[-1].lower(),
                        region=r.location or "eastus",
                        sku=getattr(r.sku, "name", None) if r.sku else None,
                        tags=r.tags or {},
                    )
                )
            return out

        return await asyncio.to_thread(_list)

    async def get_billing(self, start: date, end: date) -> list[BillingEntryDTO]:
        if self.demo_mode:
            return simulated_billing("azure", start, end)
        raise NotImplementedError(
            "Live Azure billing is not implemented. Wire CostManagementClient.query.usage() "
            "here. Until then, set DEMO_MODE=true — returning simulated costs for a real "
            "subscription would make the agents raise anomalies against figures that were "
            "never billed."
        )

    async def get_metrics(
        self, provider_resource_id: str, metric: str, days: int
    ) -> list[MetricSampleDTO]:
        if self.demo_mode:
            return simulated_metrics("azure", provider_resource_id, metric, days)
        raise NotImplementedError(
            "Live Azure metrics are not implemented. Wire MonitorManagementClient.metrics.list() "
            "here; simulated utilization must not drive rightsizing advice on real VMs."
        )
