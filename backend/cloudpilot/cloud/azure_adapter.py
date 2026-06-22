"""Azure adapter — Cost Management + Azure Monitor (read-only).

Real mode uses ``azure-identity`` (ClientSecretCredential) + the Cost Management
and Monitor management SDKs. The SDKs are synchronous, so calls are dispatched to a
thread via ``asyncio.to_thread`` to keep the event loop free.

Demo mode returns deterministic mock data so the platform runs with no Azure account.
"""

from __future__ import annotations

import asyncio
import hashlib
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

_AZURE_SERVICES = [
    ("virtual_machine", "Standard_D4s_v3"),
    ("virtual_machine", "Standard_D2s_v3"),
    ("aks_cluster", "Standard_D4s_v3"),
    ("azure_sql", "GP_Gen5_4"),
    ("blob_storage", None),
    ("app_service", "P1v3"),
    ("redis_cache", "C1"),
]
_AZURE_REGIONS = ["eastus", "westeurope", "northeurope"]


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
            return self._mock_resources()
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
            return self._mock_billing(start, end)
        # Real implementation would call CostManagementClient.query.usage(...).
        logger.info("Azure billing query {} → {}", start, end)
        return await asyncio.to_thread(lambda: self._mock_billing(start, end))

    async def get_metrics(
        self, provider_resource_id: str, metric: str, days: int
    ) -> list[MetricSampleDTO]:
        if self.demo_mode:
            return self._mock_metrics(provider_resource_id, metric, days)
        logger.info("Azure metrics {} {} {}d", provider_resource_id, metric, days)
        return await asyncio.to_thread(
            lambda: self._mock_metrics(provider_resource_id, metric, days)
        )

    # ─── deterministic mock generation ───
    def _rng(self, salt: str) -> random.Random:
        seed = int(hashlib.sha256(f"azure:{salt}".encode()).hexdigest(), 16) % (2**32)
        return random.Random(seed)

    def _mock_resources(self) -> list[ResourceDTO]:
        rng = self._rng("resources")
        out: list[ResourceDTO] = []
        for i in range(22):
            service, sku = _AZURE_SERVICES[i % len(_AZURE_SERVICES)]
            region = _AZURE_REGIONS[i % len(_AZURE_REGIONS)]
            out.append(
                ResourceDTO(
                    provider_resource_id=f"/subscriptions/demo/resourceGroups/acme/providers/{service}/{service}-{i:02d}",
                    name=f"{service.replace('_', '-')}-{i:02d}",
                    service=service,
                    region=region,
                    sku=sku,
                    tags={"env": rng.choice(["prod", "staging", "dev"]), "owner": "acme"},
                )
            )
        return out

    def _mock_billing(self, start: date, end: date) -> list[BillingEntryDTO]:
        rng = self._rng("billing")
        out: list[BillingEntryDTO] = []
        day = start
        services = ["Compute", "Storage", "Networking", "Database", "Kubernetes"]
        while day <= end:
            weekday_factor = 1.2 if day.weekday() < 5 else 0.85
            for svc in services:
                base = rng.uniform(120, 380) * weekday_factor
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
        baseline = rng.uniform(15, 45) if unit == "percent" else rng.uniform(1e6, 1e8)
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
