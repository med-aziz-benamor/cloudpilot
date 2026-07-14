"""Cloud provider adapter contract and DTOs.

Every provider integration implements :class:`CloudProviderAdapter`. The platform
is **read-only by design** — adapters expose only get/validate operations and never
create, update or delete cloud resources.

When ``DEMO_MODE`` is on (or credentials are absent), adapters return deterministic
mock data so the platform is fully functional with no real cloud account.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from cloudpilot.config import settings
from cloudpilot.models.cloud_account import CloudProvider


@dataclass(slots=True)
class ResourceDTO:
    provider_resource_id: str
    name: str
    service: str
    region: str
    sku: str | None = None
    #: Instances of ``sku`` billed by this resource (a node pool bills its node count).
    node_count: int = 1
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BillingEntryDTO:
    usage_date: date
    service: str
    cost_usd: float
    raw_currency: str = "USD"
    raw_amount: float = 0.0
    provider_resource_id: str | None = None


@dataclass(slots=True)
class MetricSampleDTO:
    metric_name: str
    timestamp: datetime
    value: float
    unit: str


class CloudProviderAdapter(ABC):
    """Read-only adapter for one cloud provider."""

    provider: CloudProvider

    def __init__(self, credentials: dict[str, Any] | None = None) -> None:
        self.credentials = credentials or {}

    @property
    def demo_mode(self) -> bool:
        """True when the adapter should serve mock data."""
        return settings.DEMO_MODE or not self.credentials

    @abstractmethod
    async def get_resources(self) -> list[ResourceDTO]:
        """Return the inventory of resources for this account."""

    @abstractmethod
    async def get_billing(self, start: date, end: date) -> list[BillingEntryDTO]:
        """Return daily billing entries in ``[start, end]``."""

    @abstractmethod
    async def get_metrics(
        self, provider_resource_id: str, metric: str, days: int
    ) -> list[MetricSampleDTO]:
        """Return time-series samples for one resource metric."""

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """Return True if the stored credentials authenticate successfully."""


def get_adapter(
    provider: CloudProvider, credentials: dict[str, Any] | None = None
) -> CloudProviderAdapter:
    """Factory returning the adapter for a provider."""
    # Imported lazily to avoid heavy SDK imports at module load time.
    from cloudpilot.cloud.aws_adapter import AWSAdapter
    from cloudpilot.cloud.azure_adapter import AzureAdapter
    from cloudpilot.cloud.gcp_adapter import GCPAdapter

    mapping: dict[CloudProvider, type[CloudProviderAdapter]] = {
        CloudProvider.AZURE: AzureAdapter,
        CloudProvider.AWS: AWSAdapter,
        CloudProvider.GCP: GCPAdapter,
    }
    return mapping[provider](credentials)
